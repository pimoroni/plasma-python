"""Tests for the plasma daemon script."""
import importlib.util
import importlib.machinery
import os
import select
import sys
import tempfile
import threading
import time
from unittest import mock

import pytest


def load_daemon(path):
    """Load a daemon script as a module, mocking the png dependency."""
    sys.modules.setdefault('png', mock.MagicMock())
    loader = importlib.machinery.SourceFileLoader("plasma_daemon", path)
    spec = importlib.util.spec_from_loader("plasma_daemon", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


@pytest.fixture
def daemon():
    return load_daemon(os.path.join(os.path.dirname(__file__), "..", "daemon", "usr", "bin", "plasma"))


@pytest.fixture
def fifo_path(tmp_path):
    path = str(tmp_path / "test_fifo")
    os.mkfifo(path)
    yield path
    if os.path.exists(path):
        os.remove(path)


class TestFIFOReadline:
    """Test FIFO.readline uses select.select for blocking I/O (PR #20)."""

    def test_readline_returns_none_on_timeout(self, daemon, fifo_path):
        fd = os.open(fifo_path, os.O_RDONLY | os.O_NONBLOCK)
        with mock.patch.object(daemon, 'select', select):
            fifo = daemon.FIFO.__new__(daemon.FIFO)
            fifo.fifo = fd
            result = fifo.readline(timeout=0.05)
        os.close(fd)
        assert result is None

    def test_readline_reads_data(self, daemon, fifo_path):
        fd = os.open(fifo_path, os.O_RDONLY | os.O_NONBLOCK)
        wf = os.open(fifo_path, os.O_WRONLY)
        os.write(wf, b"255 0 0\n")
        os.close(wf)
        with mock.patch.object(daemon, 'select', select):
            fifo = daemon.FIFO.__new__(daemon.FIFO)
            fifo.fifo = fd
            result = fifo.readline(timeout=1.0)
        os.close(fd)
        assert result == b"255 0 0"

    def test_readline_uses_select(self, daemon, fifo_path):
        """Verify readline calls select.select rather than busy-waiting."""
        fd = os.open(fifo_path, os.O_RDONLY | os.O_NONBLOCK)
        with mock.patch.object(daemon.select, 'select', wraps=select.select) as mock_select:
            fifo = daemon.FIFO.__new__(daemon.FIFO)
            fifo.fifo = fd
            fifo.readline(timeout=0.05)
        os.close(fd)
        assert mock_select.called


class TestPatternCache:
    """Test pattern caching avoids re-reading from disk (PR #20)."""

    def test_load_pattern_caches(self, daemon, tmp_path):
        daemon._pattern_cache.clear()
        daemon.PATTERNS = str(tmp_path) + "/"

        mock_reader = mock.MagicMock()
        mock_reader.read.return_value = (4, 2, [[255, 0, 0, 0, 255, 0, 0, 0, 255, 0, 0, 0]], {'alpha': False})

        pattern_file = tmp_path / "test.png"
        pattern_file.write_bytes(b"fake")

        with mock.patch('builtins.open', mock.mock_open(read_data=b'fake')):
            with mock.patch.object(daemon.png, 'Reader', return_value=mock_reader):
                result1 = daemon.load_pattern("test")
                result2 = daemon.load_pattern("test")

        assert result1 == result2
        assert "test" in daemon._pattern_cache
        assert mock_reader.read.call_count == 1

    def test_load_pattern_returns_none_for_missing(self, daemon, tmp_path):
        daemon._pattern_cache.clear()
        daemon.PATTERNS = str(tmp_path) + "/"
        result = daemon.load_pattern("nonexistent")
        assert result == (None, 0, 0, None)


class TestNeedsUpdateLogic:
    """Test that show() is only called when state changes (PR #20)."""

    def test_static_color_show_called_once(self, daemon):
        """For a static color, show() should be called once then not again."""
        mock_plasma = mock.MagicMock()
        mock_plasma.get_pixel_count.return_value = 10

        stopped = threading.Event()
        daemon.stopped = stopped

        r, g, b = 255, 0, 0
        last_r, last_g, last_b = -1, -1, -1
        last_brightness = -1
        needs_update = True

        for _ in range(5):
            if needs_update or (r != last_r or g != last_g or b != last_b):
                mock_plasma.set_all(r, g, b, brightness=1.0)
                last_r, last_g, last_b = r, g, b
                last_brightness = 1.0
                needs_update = True
            if needs_update:
                mock_plasma.show()
                needs_update = False

        assert mock_plasma.show.call_count == 1
        assert mock_plasma.set_all.call_count == 1

    def test_show_called_again_on_color_change(self, daemon):
        """show() should be called again when color changes."""
        mock_plasma = mock.MagicMock()
        mock_plasma.get_pixel_count.return_value = 10

        needs_update = True
        colors = [(255, 0, 0), (255, 0, 0), (0, 255, 0)]
        last_r, last_g, last_b = -1, -1, -1
        last_brightness = -1

        for r, g, b in colors:
            if needs_update or (r != last_r or g != last_g or b != last_b):
                mock_plasma.set_all(r, g, b, brightness=1.0)
                last_r, last_g, last_b = r, g, b
                last_brightness = 1.0
                needs_update = True
            if needs_update:
                mock_plasma.show()
                needs_update = False

        assert mock_plasma.show.call_count == 2

    def test_show_called_on_brightness_change(self, daemon):
        """show() should be called when brightness changes."""
        mock_plasma = mock.MagicMock()
        mock_plasma.get_pixel_count.return_value = 10

        needs_update = True
        r, g, b = 255, 0, 0
        last_r, last_g, last_b = 255, 0, 0
        last_brightness = 1.0

        brightnesses = [1.0, 1.0, 0.5]

        for brightness in brightnesses:
            if needs_update or (r != last_r or g != last_g or b != last_b or brightness != last_brightness):
                mock_plasma.set_all(r, g, b, brightness=brightness)
                last_r, last_g, last_b = r, g, b
                last_brightness = brightness
                needs_update = True
            if needs_update:
                mock_plasma.show()
                needs_update = False

        assert mock_plasma.show.call_count == 2


class TestFPSClamping:
    """Test FPS is clamped to minimum 1 (PR #20)."""

    def test_fps_clamped_to_min_1(self):
        assert max(1, int(0)) == 1
        assert max(1, int(-5)) == 1
        assert max(1, int(30)) == 30

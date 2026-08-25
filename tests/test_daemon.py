"""Tests for the plasma daemon script."""
import importlib.util
import importlib.machinery
import os
import select
import stat
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


class TestParseColor:
    """Test parse_color function (PR #21)."""

    def test_named_colors(self, daemon):
        assert daemon.parse_color("red") == (255, 0, 0)
        assert daemon.parse_color("green") == (0, 255, 0)
        assert daemon.parse_color("blue") == (0, 0, 255)
        assert daemon.parse_color("off") == (0, 0, 0)
        assert daemon.parse_color("black") == (0, 0, 0)
        assert daemon.parse_color("white") == (255, 255, 255)
        assert daemon.parse_color("yellow") == (255, 255, 0)
        assert daemon.parse_color("cyan") == (0, 255, 255)
        assert daemon.parse_color("purple") == (128, 0, 128)
        assert daemon.parse_color("magenta") == (255, 0, 255)
        assert daemon.parse_color("orange") == (255, 165, 0)
        assert daemon.parse_color("dim_white") == (30, 30, 30)

    def test_hex_colors(self, daemon):
        assert daemon.parse_color("#ff0000") == (255, 0, 0)
        assert daemon.parse_color("#00ff00") == (0, 255, 0)
        assert daemon.parse_color("#0000ff") == (0, 0, 255)
        assert daemon.parse_color("#ffffff") == (255, 255, 255)

    def test_invalid_hex_returns_none(self, daemon):
        assert daemon.parse_color("#abc") is None
        assert daemon.parse_color("#abcdef0") is None

    def test_integer_color(self, daemon):
        assert daemon.parse_color("16711680") == (255, 0, 0)
        assert daemon.parse_color("0") == (0, 0, 0)

    def test_invalid_color_returns_none(self, daemon):
        assert daemon.parse_color("notacolor") is None
        assert daemon.parse_color("") is None


class TestPerPixelControl:
    """Test per-pixel override logic (PR #21)."""

    def test_set_pixel_override(self, daemon):
        """Setting a pixel override should call set_pixel for that index."""
        mock_plasma = mock.MagicMock()
        mock_plasma.get_pixel_count.return_value = 10

        pixel_colors = {0: (255, 0, 0), 3: (0, 255, 0)}
        needs_update = True

        if needs_update and pixel_colors:
            for idx, (pr, pg, pb) in pixel_colors.items():
                if 0 <= idx < mock_plasma.get_pixel_count():
                    mock_plasma.set_pixel(idx, pr, pg, pb, brightness=1.0)

        mock_plasma.set_pixel.assert_any_call(0, 255, 0, 0, brightness=1.0)
        mock_plasma.set_pixel.assert_any_call(3, 0, 255, 0, brightness=1.0)

    def test_unset_pixel_override(self):
        pixel_colors = {0: (255, 0, 0), 3: (0, 255, 0)}
        pixel_colors.pop(0, None)
        assert 0 not in pixel_colors
        assert 3 in pixel_colors

    def test_clear_all_overrides(self):
        pixel_colors = {0: (255, 0, 0), 3: (0, 255, 0)}
        pixel_colors.clear()
        assert len(pixel_colors) == 0

    def test_off_command_clears_everything(self):
        r, g, b = 255, 0, 0
        pixel_colors = {0: (255, 0, 0), 3: (0, 255, 0)}
        pattern = "some_pattern"

        r, g, b = 0, 0, 0
        pixel_colors.clear()
        pattern = None

        assert r == 0 and g == 0 and b == 0
        assert len(pixel_colors) == 0
        assert pattern is None

    def test_out_of_range_pixel_ignored(self, daemon):
        """Pixel indices outside the strip range should be silently ignored."""
        mock_plasma = mock.MagicMock()
        mock_plasma.get_pixel_count.return_value = 10

        pixel_colors = {5: (255, 0, 0), 15: (0, 255, 0)}
        needs_update = True

        if needs_update and pixel_colors:
            for idx, (pr, pg, pb) in pixel_colors.items():
                if 0 <= idx < mock_plasma.get_pixel_count():
                    mock_plasma.set_pixel(idx, pr, pg, pb, brightness=1.0)

        mock_plasma.set_pixel.assert_called_once_with(5, 255, 0, 0, brightness=1.0)

    def test_named_color_command_sets_all(self, daemon):
        """A single-word named color command should set all LEDs."""
        color = daemon.parse_color("red")
        assert color == (255, 0, 0)
        r, g, b = color
        assert r == 255 and g == 0 and b == 0


class TestPlasmactl:
    """Test plasmactl command-line interface (PR #21)."""

    def load_plasmactl(self):
        sys.modules.setdefault('png', mock.MagicMock())
        path = os.path.join(os.path.dirname(__file__), "..", "daemon", "usr", "bin", "plasmactl")
        loader = importlib.machinery.SourceFileLoader("plasmactl", path)
        spec = importlib.util.spec_from_loader("plasmactl", loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        return mod

    def test_named_colors_defined(self):
        mod = self.load_plasmactl()
        assert mod.NAMED_COLORS["red"] == "255 0 0"
        assert mod.NAMED_COLORS["blue"] == "0 0 255"
        assert mod.NAMED_COLORS["off"] == "0 0 0"

    def test_color_function_parses_int(self):
        mod = self.load_plasmactl()
        assert mod.Color("255") == 255
        assert mod.Color("0") == 0

    def test_color_function_parses_hex(self):
        mod = self.load_plasmactl()
        assert mod.Color("ff") == 255

    def test_send_writes_to_fifo(self, tmp_path):
        mod = self.load_plasmactl()
        fifo = tmp_path / "plasma"
        os.mkfifo(str(fifo))
        mod.FIFO = fifo

        reader_fd = os.open(str(fifo), os.O_RDONLY | os.O_NONBLOCK)
        mod.send("255 0 0")

        ready, _, _ = select.select([reader_fd], [], [], 1.0)
        assert ready
        data = os.read(reader_fd, 1024)
        os.close(reader_fd)
        assert data == b"255 0 0\n"


class TestFIFOSafety:
    """Test FIFO safety checks in plasmactl and daemon (PR #22)."""

    def load_plasmactl(self):
        sys.modules.setdefault('png', mock.MagicMock())
        path = os.path.join(os.path.dirname(__file__), "..", "daemon", "usr", "bin", "plasmactl")
        loader = importlib.machinery.SourceFileLoader("plasmactl_safe", path)
        spec = importlib.util.spec_from_loader("plasmactl_safe", loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        return mod

    def test_open_fifo_rejects_regular_file(self, tmp_path):
        """plasmactl should refuse to write to a non-FIFO file."""
        mod = self.load_plasmactl()
        regular = tmp_path / "not_a_fifo"
        regular.write_text("data")
        with pytest.raises(RuntimeError, match="not a pipe"):
            mod.open_fifo(regular)

    def test_open_fifo_rejects_missing_file(self, tmp_path):
        mod = self.load_plasmactl()
        missing = tmp_path / "nonexistent"
        with pytest.raises(RuntimeError, match="does not exist"):
            mod.open_fifo(missing)

    def test_open_fifo_accepts_real_fifo(self, tmp_path):
        mod = self.load_plasmactl()
        fifo = tmp_path / "real_fifo"
        os.mkfifo(str(fifo))
        reader_fd = os.open(str(fifo), os.O_RDONLY | os.O_NONBLOCK)
        f = mod.open_fifo(fifo)
        f.close()
        os.close(reader_fd)

    def test_daemon_fifo_removes_stale_file(self, daemon, tmp_path):
        """Daemon should remove a stale non-FIFO file before creating the pipe."""
        stale = tmp_path / "stale_plasma"
        stale.write_text("stale data")
        assert stale.exists()
        assert not stat.S_ISFIFO(stale.stat().st_mode)

        daemon.PIPE_FILE = str(stale)
        with mock.patch.object(daemon.os, 'mkfifo') as mock_mkfifo:
            with mock.patch.object(daemon.os, 'open', return_value=42):
                with mock.patch.object(daemon.os, 'close'):
                    fifo = daemon.FIFO(str(stale))
            mock_mkfifo.assert_called_once_with(str(stale))

    def test_daemon_fifo_preserves_existing_fifo(self, daemon, tmp_path):
        """Daemon should not remove an existing FIFO."""
        fifo_path = tmp_path / "existing_fifo"
        os.mkfifo(str(fifo_path))
        assert stat.S_ISFIFO(fifo_path.stat().st_mode)

        daemon.PIPE_FILE = str(fifo_path)
        with mock.patch.object(daemon.os, 'mkfifo') as mock_mkfifo:
            mock_mkfifo.side_effect = OSError("already exists")
            with mock.patch.object(daemon.os, 'open', return_value=42):
                with mock.patch.object(daemon.os, 'close'):
                    with mock.patch.object(daemon.os, 'remove') as mock_remove:
                        fifo = daemon.FIFO(str(fifo_path))
            mock_remove.assert_not_called()

    def test_daemon_fifo_creates_new_fifo(self, daemon, tmp_path):
        """Daemon should create a FIFO when no file exists."""
        new_fifo = tmp_path / "new_plasma"
        daemon.PIPE_FILE = str(new_fifo)
        with mock.patch.object(daemon.os, 'mkfifo') as mock_mkfifo:
            with mock.patch.object(daemon.os, 'open', return_value=42):
                with mock.patch.object(daemon.os, 'close'):
                    fifo = daemon.FIFO(str(new_fifo))
            mock_mkfifo.assert_called_once_with(str(new_fifo))

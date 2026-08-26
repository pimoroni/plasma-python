import pytest


def test_get_device_matrix(config_file):
    from plasma import get_device

    _device, _args = get_device(config_file)


def test_get_device_raises_valueerror():
    from plasma import get_device
    with pytest.raises(ValueError):
        get_device("XXXXXX")


def test_get_device_apa102():
    from plasma import get_device
    from plasma.apa102 import PlasmaAPA102

    device, _args = get_device("APA102:14:15")

    assert device == PlasmaAPA102


def test_get_device_ws281x():
    from plasma import get_device
    from plasma.ws281x import PlasmaWS281X

    device, _args = get_device("WS281X:13:WS2812")

    assert device == PlasmaWS281X


def test_get_device_serial(serial):
    from plasma import get_device
    from plasma.serial import PlasmaSerial

    device, _args = get_device("SERIAL:/dev/ttyACM0")

    assert device == PlasmaSerial

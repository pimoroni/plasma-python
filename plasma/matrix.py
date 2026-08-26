"""Combine multiple LED strip types into a single logical strip."""
import contextlib
import pathlib

import yaml


class PlasmaMatrix:
    """Combine multiple LED strip types into a single logical strip."""

    def __init__(self, config_file=None):
        """Initialise a matrix.

        :param config_file: Path to yml configuration file

        """
        self._devices = {}

        if type(config_file) is str:
            config_file = pathlib.Path(config_file)

        if not config_file.is_file():
            raise ValueError(f"Could not find {config_file}")

        with open(config_file) as config:
            self._config = yaml.safe_load(config)

        for required in ("pixels", "devices"):
            if required not in self._config:
                raise ValueError(f"Config missing required setting: '{required}'")

        self._pixel_count = int(self._config["pixels"])

        for output_name, output_options in self._config["devices"].items():
            enabled = output_options.get("enabled", True)
            if not enabled:
                continue

            output_type = output_options.get("type")
            pixels = output_options.get("pixels", self._pixel_count)
            offset = output_options.get("offset", 0)

            del output_options["type"]

            with contextlib.suppress(KeyError):
                del output_options["enabled"]

            with contextlib.suppress(KeyError):
                del output_options["pixels"]

            with contextlib.suppress(KeyError):
                del output_options["offset"]

            output_device = self.get_output_device(output_type)

            self._devices[output_name] = {
                'offset': offset,
                'type': output_type,
                'device': output_device(pixels, **output_options)
            }

    def get_pixel_count(self):
        """Get the count of pixels."""
        return self._pixel_count

    def get_device_count(self):
        """Get the count of output devices."""
        return len(self._devices)

    def get_device(self, index):
        """Get a device by name or type.

        If a string (type) is given, it will try to find a device with that name.

        Otherwise returns first device of that type.

        """
        if index in self._devices:
            return self._devices[index].get('device')

        if isinstance(index, str):
            for d in self._devices.values():
                if d.get('type') == index:
                    return d.get('device')

        raise ValueError(f"Invalid device index {index}")

    def get_output_device(self, output_type):
        """Get output class by name."""
        output_type = output_type.upper()
        if output_type in ["GPIO", "APA102"]:
            from .gpio import PlasmaGPIO
            return PlasmaGPIO
        if output_type in ["USB", "SERIAL"]:
            from .usb import PlasmaSerial
            return PlasmaSerial
        if output_type == "WS281X":
            from .ws281x import PlasmaWS281X
            return PlasmaWS281X
        raise ValueError(f"Invalid output type {output_type}!")

    def set_light(self, index, r, g, b, brightness=None):
        """Set the RGB colour of an individual light in your matrix."""
        raise NotImplementedError("Use get_device(index).set_light()")

    def set_all(self, r, g, b, brightness=None):
        """Set the RGB value and optionally brightness of all pixels."""
        for d in self._devices.values():
            d.get('device').set_all(r, g, b, brightness=brightness)

    def set_sequence(self, sequence):
        """Set all LEDs from a buffer of individual colours."""
        if type(sequence) is list:
            for index, led in enumerate(sequence):
                self.set_pixel(index, *led)
        elif type(sequence) is dict:
            for index, led in sequence.items():
                self.set_pixel(index, *led)
        else:
            for index, led in sequence:
                self.set_pixel(index, *led)

    def get_pixel(self, x):
        """Get the RGB and brightness value of a specific pixel."""
        for d in self._devices.values():
            device = d.get('device')
            offset = d.get('offset')
            count = device.get_pixel_count()

            if x >= offset and x < offset + count:
                return device.get_pixel(x - offset)

    def set_pixel(self, x, r, g, b, brightness=None):
        """Set the RGB value, and optionally brightness, of a single pixel."""
        for d in self._devices.values():
            device = d.get('device')
            offset = d.get('offset')
            count = device.get_pixel_count()

            if x >= offset and x < offset + count:
                device.set_pixel(x - offset, r, g, b, brightness=brightness)

    def show(self):
        """Display lights across devices.

        Sets each device in turn, picking the pixels
        from the buffer starting from the specified offset.

        """
        for d in self._devices.values():
            d.get('device').show()

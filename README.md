# Plasma: LED Sequencing

Plasma is an LED/Light sequencing suite written to harmonise a variety of LED strand/board types and interfaces into a standard API for write-once-run-anywhere lighting code.

Plasma also includes plasmad, a system daemon for sequencing light strips using PNG images to provide animation frames.

[![Build Status](https://img.shields.io/github/actions/workflow/status/pimoroni/plasma-python/test.yml?branch=master)](https://github.com/pimoroni/plasma-python/actions/workflows/test.yml)
[![Coverage Status](https://coveralls.io/repos/github/pimoroni/plasma-python/badge.svg?branch=master)](https://coveralls.io/github/pimoroni/plasma-python?branch=master)
[![PyPi Package](https://img.shields.io/pypi/v/plasmalights.svg)](https://pypi.python.org/pypi/plasmalights)
[![Python Versions](https://img.shields.io/pypi/pyversions/plasmalights.svg)](https://pypi.python.org/pypi/plasmalights)

## Compatible Products

Plasma was originally written to provide an easy way to sequence lights and swap out patterns for the Pimoroni Plasma kit.

- https://shop.pimoroni.com/products/picade-plasma-kit-illuminated-arcade-buttons
- https://shop.pimoroni.com/products/player-x-usb-games-controller-pcb
- https://shop.pimoroni.com/products/blinkt
- https://shop.pimoroni.com/products/unicorn-hat
- https://shop.pimoroni.com/products/unicorn-phat

## Installing

### Full install (recommended):

We've created an easy installation script that will install all pre-requisites and get your Plasma Arcade Button Lights
up and running with minimal efforts. To run it, fire up Terminal which you'll find in Menu -> Accessories -> Terminal
on your Raspberry Pi desktop, as illustrated below:

![Finding the terminal](http://get.pimoroni.com/resources/github-repo-terminal.png)

In the new terminal window type the command exactly as it appears below (check for typos) and follow the on-screen instructions:

```bash
curl https://get.pimoroni.com/plasma | bash
```

If you choose to download examples you'll find them in `/home/pi/Pimoroni/plasma/`.

### Manual install:

```bash
python3 -m pip install plasmalights
```

### Using Plasma Daemon

To install the Plasma daemon you should clone this repository, navigate to the "daemon" directory and run the installer:

```
git clone https://github.com/pimoroni/plasma-python
cd plasma-python/daemon
sudo ./install
```

---

Note: If you're using Picade Player X you should edit daemon/etc/systemd/system/plasma.service and change the output device option from `-o GPIO:15:14` to `-o SERIAL:/dev/ttyACM0`. If you're using Unicorn HAT or pHAT you should use `-o WS281X:WS2812:18:0`.

If you're using GPIO on a Picade HAT you can adjust the pins accordingly using `-o GPIO:<data>:<clock>` where data and clock are valid BCM pins. If you're using the old Plasma/Hack header you may need to swap from `-o GPIO:15:14` to `-o GPIO:14:15` depending on how your connections are wired.

---

The Plasma daemon installer installs two programs onto your Raspberry Pi. `plasma` itself and a tool called `plasmactl` you can use to install and switch lighting effects. Plasma runs as a service on your system.

`plasmactl` commands:

* `plasmactl 255 0 0` - Set Plasma lights to R, G, B colour. Red in this case.
* `plasmactl <pattern>` - Set Plasma lights to pattern image
* `plasmactl --fps <fps>` - Change plasma effect framerate (default is 30, lower FPS = less CPU)
* `plasmactl --brightness <0.0-1.0>` - Set LED brightness
* `plasmactl --list` - List all available patterns
* `sudo plasmactl --install <pattern>` - Install a new pattern, where `<pattern>` is the filename of a 24bit PNG image file
* `plasmactl --set <index> <color>` - Set a single pixel to a named color (e.g. `red`, `blue`, `dim_white`)
* `plasmactl --set <index> <r> <g> <b>` - Set a single pixel to an RGB colour
* `plasmactl --unset <index>` - Clear a per-pixel override
* `plasmactl --clear` - Clear all per-pixel overrides
* `plasmactl --off` - Turn all LEDs off
* `plasmactl --color <r> <g> <b>` - Alias for `--colour`

Named colours: `off`, `black`, `white`, `red`, `green`, `blue`, `yellow`, `cyan`, `purple`, `magenta`, `orange`, `dim_white`. Hex colours (e.g. `#ff0000`) are also supported.

### Pipe protocol

External applications can control the Plasma daemon by writing commands to the FIFO pipe at `/tmp/plasma`:

```
echo "255 0 0" > /tmp/plasma          # Set all LEDs to red
echo "red" > /tmp/plasma              # Set all LEDs to red (named color)
echo "set 0 255 0 0" > /tmp/plasma    # Set pixel 0 to red
echo "set 1 blue" > /tmp/plasma       # Set pixel 1 to blue (named color)
echo "set 2 #00ff00" > /tmp/plasma     # Set pixel 2 to green (hex color)
echo "unset 0" > /tmp/plasma          # Clear per-pixel override on pixel 0
echo "clear" > /tmp/plasma            # Clear all per-pixel overrides
echo "off" > /tmp/plasma             # Turn all LEDs off
echo "fps 10" > /tmp/plasma          # Change framerate to 10fps
echo "brightness 0.5" > /tmp/plasma   # Set brightness to 50%
echo "mypattern" > /tmp/plasma        # Switch to a PNG pattern
echo "stop" > /tmp/plasma            # Stop the daemon
```

### Development:

If you want to contribute, or like living on the edge of your seat by having the latest code, you should clone this repository and run:

```bash
./install.sh --unstable
```

## Documentation & Support

* Guides and tutorials - https://learn.pimoroni.com/
* Get help - http://forums.pimoroni.com/c/support

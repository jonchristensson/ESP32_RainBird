"""
OTA update via WebREPL.

WebREPL is built into MicroPython and runs a password-protected WebSocket server
on port 8266. After start() is called, files can be pushed from a PC using
webrepl_cli.py without physical access to the device.

Setup (one-time, already done if you ran import webrepl; webrepl.setup()):
  The webrepl_cfg.py file in this project sets the password from secrets.py.
  WebREPL is enabled by boot.py importing ota and calling ota.start().

Push a file from PC:
  python webrepl_cli.py -p <OTA_PASSWORD> <local_file.py> <device_ip>:<remote_file.py>

Download webrepl_cli.py from:
  https://raw.githubusercontent.com/micropython/webrepl/master/webrepl_cli.py

After pushing all updated files, reboot the device:
  python webrepl_cli.py -p <OTA_PASSWORD> --reboot <device_ip>
  (or push a main.py that imports machine; machine.reset() at top level)
"""

import webrepl


def start() -> None:
    """Start the WebREPL OTA listener. Called from boot.py after WiFi connects."""
    try:
        webrepl.start()
        print("OTA: WebREPL started on port 8266")
    except ValueError:
        print("OTA: WebREPL failed to start — password must be 4-9 characters (check OTA_PASSWORD in secrets.py)")

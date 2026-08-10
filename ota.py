"""
OTA update via WebREPL.

WebREPL is built into MicroPython and runs a password-protected WebSocket server
on port 8266. After start() is called, files can be pushed from a PC using
tools/webrepl_cli.py without physical access to the device.

Setup (one-time, already done if you ran import webrepl; webrepl.setup()):
  The webrepl_cfg.py file in this project sets the password from secrets.py.
  WebREPL is enabled by boot.py importing ota and calling ota.start().

Push a file from PC (run from the repo root):
  python tools/webrepl_cli.py -p <OTA_PASSWORD> <local_file.py> <device_ip>:<remote_file.py>

tools/webrepl_cli.py is already vendored in this repo — no download needed.

After pushing all updated files, reboot the device by power-cycling it, or use
the WebREPL browser client to reboot — see docs/instructions/04-wireless-maintenance.html.
  Note: the --reboot flag shown in some webrepl docs does not exist in webrepl_cli.py.
"""

import webrepl


def start() -> None:
    """Start the WebREPL OTA listener. Called from boot.py after WiFi connects."""
    try:
        webrepl.start()
        print("OTA: WebREPL started on port 8266")
    except ValueError:
        print("OTA: WebREPL failed to start — password must be 4-9 characters (check OTA_PASSWORD in secrets.py)")

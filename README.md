# ESP32 Rain Sensor

MicroPython firmware for an ESP32-WROOM-32U that replaces a broken rain sensor on a Rain Bird ESP-ME sprinkler controller. Instead of measuring rain physically, it checks the [Open-Meteo API](https://open-meteo.com/) over WiFi for recent and forecasted rainfall, then controls a relay wired to the Rain Bird's sensor terminals to pause or allow irrigation.

**Design goals:**
- Self-contained — no server, no Home Assistant, no cloud dependency beyond the weather API
- Fail-open — if anything goes wrong (WiFi down, API unreachable, power loss, a bad firmware push), irrigation runs normally
- Predictive — skips irrigation based on upcoming forecast, not just rain that already fell

---

## Getting started

Building your own one of these takes four steps, in order:

1. **[Prerequisites](docs/instructions/01-prerequisites.html)** — tools to install, parts to buy, and which ESP32 variant to get
2. **[Flash & setup](docs/instructions/02-flash-guide.html)** — flash MicroPython, configure `secrets.py`, upload the firmware, verify over serial
3. **[Wiring](docs/instructions/03-wiring.html)** — wire the ESP32, relay, and power converter; bench-test before touching the Rain Bird; solder and install
4. **[Wireless & maintenance](docs/instructions/04-wireless-maintenance.html)** — day-to-day operation once the device is sealed up: pushing updates, monitoring, and recovery

Start with the prerequisites doc even if you already own an ESP32 — it covers the ESP32-32U vs 32D decision, which affects whether you need an external antenna kit.

---

## How it works

Every 15 minutes the device makes a single call to the Open-Meteo forecast API, which returns hourly precipitation data in both directions:

- **Past 6 hours** — sums hourly precipitation to get `rain_6h`
- **Next 12 hours** — sums hourly precipitation to get `forecast_12h`

It then applies two thresholds:

| Condition | Action |
|-----------|--------|
| Recent rain > 0.25" in last 6h | Energize relay → block irrigation |
| Forecast rain > 0.5" in next 12h | Energize relay → block irrigation |
| API call failed or WiFi down | De-energize relay → allow irrigation (fail-open) |
| Neither threshold exceeded | De-energize relay → allow irrigation |

The Rain Bird ESP-ME expects a **normally closed** sensor circuit. The relay is wired NC (normally closed), so the circuit is closed by default — irrigation runs. The ESP32 energizes the relay to open the circuit and block irrigation. If the ESP32 loses power or WiFi, the relay de-energizes, the circuit closes, and the Rain Bird runs normally.

HTTPS requests use full certificate verification against a bundled root CA certificate (`ca.pem`). No API key is required — Open-Meteo is free and keyless.

If a firmware push leaves the device unable to boot cleanly (three resets within 60 seconds), it drops into a safe mode that de-energizes the relay, starts WebREPL, and waits for a corrected file — see [`docs/instructions/04-wireless-maintenance.html`](docs/instructions/04-wireless-maintenance.html) for recovery steps.

---

## Hardware

- **MCU:** ESP32-WROOM-32U (or 32D if WiFi signal at the install location is strong — see the prerequisites doc)
- **Relay:** Active-high, 3.3V-logic-compatible 5V relay module (signal pin on GPIO 22)
- **Power:** An AC/DC buck converter steps the Rain Bird's 24VAC down to a calibrated 5V for the ESP32 and relay (USB works fine for bench testing before permanent installation)
- **Wiring:** Relay NC + COM terminals → Rain Bird ESP-ME sensor terminals (the two terminals labeled "SEN")

```
ESP32 GPIO 22 ──► Relay IN
ESP32 GND      ──► Relay GND
5V supply      ──► Relay VCC

Relay NC  ──► Rain Bird SEN terminal 1
Relay COM ──► Rain Bird SEN terminal 2
```

Full parts list, wiring diagrams, and bench-test procedures are in the [instruction docs](docs/instructions/).

---

## Project structure

```
├── boot.py              # Runs before main.py — disables AP interface
├── main.py              # Entry point: WiFi connect, OTA start, 15-min check loop
├── config.py            # Tunable constants (thresholds, intervals, pins); imports secrets
├── secrets_template.py  # Committed placeholder — copy to secrets.py and fill in
├── secrets.py           # Gitignored — your actual credentials
├── wifi.py              # WiFi connect, auto-reconnect every 30s, watchdog reboot at 5min
├── weather.py           # HTTPS weather client — fetches and parses Open-Meteo API responses
├── irrigation.py        # Relay control and threshold decision logic
├── status.py            # Onboard/external LED: solid / slow blink / fast blink via hardware Timer
├── ota.py               # WebREPL OTA — password-protected over-the-air updates
├── reset_tracker.py     # Boot loop detection via RTC memory — triggers safe mode
├── logger.py            # Optional Google Sheets telemetry logger (skips cleanly if unconfigured)
├── webrepl_cfg.py       # Sets WebREPL password from secrets.py
├── ca.pem               # ISRG Root X1 certificate for api.open-meteo.com TLS verification
├── google_ca.pem        # CA certificate for Google Sheets HTTPS (used by logger.py)
├── docs/
│   └── instructions/    # Numbered setup guides — see Getting Started above
└── tools/               # Host-side utilities (not uploaded to the device)
    ├── test_api.py      # Desktop test script — calls Open-Meteo API from CPython for quick verification
    └── webrepl_cli.py   # Command-line WebREPL client for pushing files over WiFi (vendored from micropython/webrepl)
```

### Module responsibilities

**`wifi.py`** — Owns the WiFi interface. `connect()` handles initial connection with a 30-second timeout. `tick()` is called every 10 seconds from the main loop: it detects drops, attempts reconnection every 30 seconds, logs attempt count and elapsed time, and triggers `machine.reset()` after 5 minutes of continuous disconnection to clear any stuck network stack state.

**`weather.py`** — Makes a single HTTPS GET request per cycle to the Open-Meteo forecast API using raw `usocket` + `ussl` with `CERT_REQUIRED` and the bundled CA cert. Sums the hourly precipitation array: first 6 values → `rain_6h`, remaining 12 → `forecast_12h`. Returns `(rain_6h: float, forecast_12h: float, success: bool)`. All network and parse errors are caught and logged; never crashes.

**`irrigation.py`** — Initializes the relay pin de-energized on import (fail-open from the first line of execution). `update()` applies thresholds from `config.py` and sets the relay; returns `'blocked'` or `'allowed'`. `allow()` forces de-energized — called when WiFi is down.

**`status.py`** — Uses MicroPython's hardware `Timer` to blink a status LED without blocking the main loop or weather checks. Three states: `"ok"` (solid on), `"rain"` (500ms timer toggle = 1s blink), `"error"` (125ms timer toggle = 250ms blink). `set_status()` is idempotent and logs transitions.

**`ota.py`** — Wraps `webrepl.start()`. WebREPL is a password-protected WebSocket server built into MicroPython that enables pushing files over WiFi. The password comes from `secrets.py` via `webrepl_cfg.py`. OTA starts after the first successful WiFi connection and runs as a background listener.

**`reset_tracker.py`** — Tracks reset frequency in RTC memory (survives reboots, cleared by a full power cycle). If three resets happen within 60 seconds of each other, `main.py` drops into safe mode instead of running the normal loop — this catches a firmware push that boot-loops the device and turns what would otherwise require physical access into a fixable-over-WiFi situation.

**`logger.py`** — Optional telemetry: POSTs each check cycle's results (event, rain readings, decision, WiFi signal, free memory, timestamp) to a Google Sheets web app over HTTPS. If `GOOGLE_SHEETS_URL` in `secrets.py` is still the template placeholder, `log()` prints a message and returns immediately — no network call, no crash, no effect on irrigation logic either way. See [`docs/instructions/01-prerequisites.html`](docs/instructions/01-prerequisites.html) for setup.

---

## Quick setup reference

Full walkthroughs with screenshots-equivalent detail are in the [numbered guides](#getting-started) — this is the condensed command reference.

### 1. Flash MicroPython

Download `ESP32_GENERIC-20241129-v1.24.1.bin` from https://micropython.org/download/ESP32_GENERIC/

```
pip install esptool
esptool.py --chip esp32 --port COM<N> erase_flash
esptool.py --chip esp32 --port COM<N> --baud 460800 write_flash -z 0x1000 ESP32_GENERIC-20241129-v1.24.1.bin
```

### 2. Create secrets.py

```
cp secrets_template.py secrets.py
```

Fill in `secrets.py`:

```python
WIFI_SSID = "your-network"
WIFI_PASSWORD = "your-password"
LATITUDE = "36.4620"    # decimal degrees
LONGITUDE = "-116.8666"
OTA_PASSWORD = "choose-a-strong-password"
GOOGLE_SHEETS_URL = "https://script.google.com/macros/s/YOUR_DEPLOYMENT_ID/exec"  # optional, see prerequisites doc
```

No API key is required — Open-Meteo is free and keyless (10,000 calls/day; this firmware uses ~96/day).

### 3. Upload files

Install mpremote: `pip install mpremote`

```
mpremote connect COM<N> cp boot.py main.py config.py wifi.py weather.py irrigation.py status.py ota.py reset_tracker.py logger.py webrepl_cfg.py secrets.py ca.pem google_ca.pem :
```

### 4. Verify on serial

```
mpremote connect COM<N> repl
```

After reset you should see boot messages, a WiFi connection line with IP address, and then weather data with rain amounts printed to serial.

---

## Configuration

All tunable constants are in `config.py`:

| Constant | Default | Description |
|----------|---------|-------------|
| `RAIN_THRESHOLD_6H` | `0.25` | Inches in last 6h that trigger blocking |
| `RAIN_THRESHOLD_12H` | `0.5` | Inches forecast in next 12h that trigger blocking |
| `CHECK_INTERVAL_S` | `900` | Seconds between weather checks (15 min) |
| `WIFI_TIMEOUT_S` | `30` | Seconds before giving up on initial WiFi connect |
| `WIFI_RECONNECT_INTERVAL_S` | `30` | Seconds between reconnect attempts |
| `WIFI_WATCHDOG_TIMEOUT_S` | `300` | Seconds disconnected before hard reboot (5 min) |
| `RELAY_PIN` | `22` | GPIO pin for relay signal |
| `LED_PIN` | `2` | GPIO pin for status LED |

To temporarily force a rain condition for testing, set `RAIN_THRESHOLD_6H = -1.0`. The comparison is strict (`rain_6h > threshold`), and `rain_6h` is a sum of API-reported precipitation that's often exactly `0.000` on a dry day — `0.0` as the threshold won't reliably trigger a block. A negative threshold guarantees it, since `rain_6h` can't be negative.

---

## LED status

Not every ESP32-WROOM-32U board has an onboard LED on GPIO2 — check yours, and wire an external LED + resistor on GPIO2 if it doesn't (see the wiring doc).

| Pattern | Meaning |
|---------|---------|
| Solid on | WiFi connected, irrigation allowed |
| Slow blink (~1s cycle) | WiFi connected, rain threshold exceeded — irrigation blocked |
| Fast blink (~250ms cycle) | WiFi disconnected or API error |

---

## OTA updates

Once the device is running and connected to WiFi, you can push updated files without physical access. The full rhythm — pushing files, rebooting, verifying, and recovering from safe mode — is in [`docs/instructions/04-wireless-maintenance.html`](docs/instructions/04-wireless-maintenance.html). Short version:

```
python tools/webrepl_cli.py -p <OTA_PASSWORD> updated_file.py <device_ip>:updated_file.py
```

`tools/webrepl_cli.py` can push files but cannot reboot the device or open an interactive prompt — for that you need the WebREPL browser client (covered in the wireless-maintenance doc), then reboot from its prompt with `import machine; machine.reset()`.

> **Security note:** MicroPython's WebREPL uses an unencrypted WebSocket (`ws://`). The OTA password is sent in plaintext over the network. This is acceptable on a trusted home network, but anyone able to observe local traffic during a push would see the password. Do not use this over an untrusted or public network.

Find the device IP in the serial output on boot, or check your router's DHCP client list — setting a DHCP reservation for the device is strongly recommended once installed (see the wireless-maintenance doc).

---

## Security considerations

This device sits on your home network and is designed to be low-risk, but it's worth understanding the tradeoffs:

- **WebREPL is unencrypted.** Both the file-push tool and the browser-based interactive client talk to the device over plain `ws://`, not `wss://`. The OTA password is visible to anything that can observe local network traffic during a push. This is the accepted tradeoff for MicroPython's built-in OTA mechanism — don't expose the device's WebREPL port (8266) to the internet, and treat your home network as the trust boundary.
- **What the optional logger sends:** if you configure Google Sheets logging, each row contains the event type, rain/forecast readings, the irrigation decision, WiFi signal strength, free memory, and a timestamp. It never sends WiFi credentials, the OTA password, or your coordinates.
- **Physical access is credential access.** `secrets.py` is stored unencrypted in the device's flash filesystem. Anyone with USB access to the board (before it's sealed into the installation) or a way to read the deployed filesystem can retrieve WiFi credentials and the OTA password. Treat the assembled device the same as any other piece of trusted network hardware in your home.
- **No inbound attack surface beyond WebREPL.** The device makes only outbound HTTPS connections (to Open-Meteo and, optionally, Google) and listens solely on port 8266 for WebREPL. It does not run a web server or expose any other listening port.

---

## Serial output

Example output on a clear day:

```
=== ESP32 Rain Sensor booting ===
Status: None -> error
WiFi: connecting to MyNetwork...
WiFi: connected, IP=<device_ip>
NTP: time synchronized
OTA: WebREPL started on port 8266
Weather: rain_6h=0.000" forecast_12h=0.000"
Irrigation: allowing — rain_6h=0.000" forecast_12h=0.000", relay de-energized
Status: error -> ok
```

Example output when rain is detected:

```
Weather: rain_6h=0.310" forecast_12h=0.120"
Irrigation: BLOCKING — recent rain 0.310" > 0.250", relay energized
Status: ok -> rain
```

Example output during WiFi outage:

```
WiFi: connection lost, starting reconnect loop
WiFi: attempting reconnect (attempt 1, 30s since drop)...
WiFi: reconnect attempt failed
Irrigation: fail-open, relay de-energized
Status: ok -> error
```

---

## License

MIT — see [LICENSE](LICENSE). Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

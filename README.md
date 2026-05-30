# ESP32 Rain Sensor

MicroPython firmware for an ESP32-WROOM-32U that replaces a broken rain sensor on a Rain Bird ESP-ME sprinkler controller. Instead of measuring rain physically, it checks the [OpenWeatherMap free 2.5 API](https://openweathermap.org/api) over WiFi for recent and forecasted rainfall, then controls a relay wired to the Rain Bird's sensor terminals to pause or allow irrigation.

**Design goals:**
- Self-contained — no server, no Home Assistant, no cloud dependency beyond the weather API
- Fail-open — if anything goes wrong (WiFi down, API unreachable, power loss), irrigation runs normally
- Predictive — skips irrigation based on upcoming forecast, not just rain that already fell

---

## How it works

Every 15 minutes the device fetches two OpenWeatherMap endpoints:

1. **Current weather** (`/data/2.5/weather`) — extracts `rain.3h`: inches that fell in the last 3 hours
2. **5-day forecast** (`/data/2.5/forecast`) — sums `rain.3h` across the first four 3-hour blocks (next 12 hours)

It then applies two thresholds:

| Condition | Action |
|-----------|--------|
| Recent rain > 0.25" in last 3h | Energize relay → block irrigation |
| Forecast rain > 0.5" in next 12h | Energize relay → block irrigation |
| API call failed or WiFi down | De-energize relay → allow irrigation (fail-open) |
| Neither threshold exceeded | De-energize relay → allow irrigation |

The Rain Bird ESP-ME expects a **normally closed** sensor circuit. The relay is wired NC (normally closed), so the circuit is closed by default — irrigation runs. The ESP32 energizes the relay to open the circuit and block irrigation. If the ESP32 loses power or WiFi, the relay de-energizes, the circuit closes, and the Rain Bird runs normally.

HTTPS requests use full certificate verification against a bundled root CA certificate (`owm_ca.pem`) so the API key is never exposed over an unencrypted connection.

---

## Hardware

- **MCU:** ESP32-WROOM-32U
- **Relay:** Any 5V relay module (signal pin on GPIO 22)
- **Wiring:** Relay NC + COM terminals → Rain Bird ESP-ME sensor terminals (the two terminals labeled "SEN")
- **Power:** 5V USB (separate supply — the Rain Bird 24VAC transformer is not used)

```
ESP32 GPIO 22 ──► Relay IN
ESP32 GND      ──► Relay GND
5V supply      ──► Relay VCC

Relay NC  ──► Rain Bird SEN terminal 1
Relay COM ──► Rain Bird SEN terminal 2
```

---

## Project structure

```
├── boot.py              # Runs before main.py — disables AP interface
├── main.py              # Entry point: WiFi connect, OTA start, 15-min check loop
├── config.py            # Tunable constants (thresholds, intervals, pins); imports secrets
├── secrets_template.py  # Committed placeholder — copy to secrets.py and fill in
├── secrets.py           # Gitignored — your actual credentials
├── network.py           # WiFi connect, auto-reconnect every 30s, watchdog reboot at 5min
├── weather.py           # HTTPS weather client — fetches and parses OWM API responses
├── irrigation.py        # Relay control and threshold decision logic
├── status.py            # Onboard LED: solid / slow blink / fast blink via hardware Timer
├── ota.py               # WebREPL OTA — password-protected over-the-air updates
├── webrepl_cfg.py       # Sets WebREPL password from secrets.py
└── owm_ca.pem           # USERTrust RSA root CA certificate for api.openweathermap.org
```

### Module responsibilities

**`network.py`** — Owns the WiFi interface. `connect()` handles initial connection with a 30-second timeout. `tick()` is called every 10 seconds from the main loop: it detects drops, attempts reconnection every 30 seconds, logs attempt count and elapsed time, and triggers `machine.reset()` after 5 minutes of continuous disconnection to clear any stuck network stack state.

**`weather.py`** — Makes two HTTPS GET requests per cycle using raw `usocket` + `ussl` with `CERT_REQUIRED` and the bundled CA cert. Extracts `rain.3h` from the current weather response (0.0 if the key is absent — common on clear days). Sums precipitation across the first 4 forecast blocks. Returns `(rain_3h: float, forecast_12h: float, success: bool)`. All network and parse errors are caught and logged; never crashes.

**`irrigation.py`** — Initializes the relay pin de-energized on import (fail-open from the first line of execution). `update()` applies thresholds from `config.py` and sets the relay; returns `'blocked'` or `'allowed'`. `allow()` forces de-energized — called when WiFi is down.

**`status.py`** — Uses MicroPython's hardware `Timer` to blink the onboard LED without blocking the main loop or weather checks. Three states: `"ok"` (solid on), `"rain"` (500ms timer toggle = 1s blink), `"error"` (125ms timer toggle = 250ms blink). `set_status()` is idempotent and logs transitions.

**`ota.py`** — Wraps `webrepl.start()`. WebREPL is a password-protected WebSocket server built into MicroPython that enables pushing files over WiFi. The password comes from `secrets.py` via `webrepl_cfg.py`. OTA starts after the first successful WiFi connection and runs as a background listener.

---

## Setup

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
OWM_API_KEY = "your-openweathermap-api-key"   # free tier works
LATITUDE = "36.4620"    # decimal degrees
LONGITUDE = "-116.8666"
OTA_PASSWORD = "choose-a-strong-password"
```

Get a free OpenWeatherMap API key at https://openweathermap.org/api — the free tier allows 1,000 calls/day; this firmware uses ~192/day.

### 3. Upload files

Install mpremote: `pip install mpremote`

```
mpremote connect COM<N> cp boot.py main.py config.py network.py weather.py irrigation.py status.py ota.py webrepl_cfg.py secrets.py owm_ca.pem :
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
| `RAIN_THRESHOLD_3H` | `0.25` | Inches in last 3h that trigger blocking |
| `RAIN_THRESHOLD_12H` | `0.5` | Inches forecast in next 12h that trigger blocking |
| `CHECK_INTERVAL_S` | `900` | Seconds between weather checks (15 min) |
| `WIFI_TIMEOUT_S` | `30` | Seconds before giving up on initial WiFi connect |
| `WIFI_RECONNECT_INTERVAL_S` | `30` | Seconds between reconnect attempts |
| `WIFI_WATCHDOG_TIMEOUT_S` | `300` | Seconds disconnected before hard reboot (5 min) |
| `RELAY_PIN` | `22` | GPIO pin for relay signal |
| `LED_PIN` | `2` | GPIO pin for onboard LED |

To temporarily force a rain condition for testing, set `RAIN_THRESHOLD_3H = 0.0` — any non-zero recent rain will trigger blocking.

---

## LED status

| Pattern | Meaning |
|---------|---------|
| Solid on | WiFi connected, irrigation allowed |
| Slow blink (~1s cycle) | WiFi connected, rain threshold exceeded — irrigation blocked |
| Fast blink (~250ms cycle) | WiFi disconnected or API error |

---

## OTA updates

Once the device is running and connected to WiFi, you can push updated files without physical access.

Download the WebREPL CLI tool:
```
curl -O https://raw.githubusercontent.com/micropython/webrepl/master/webrepl_cli.py
```

Push a file:
```
python webrepl_cli.py -p <OTA_PASSWORD> updated_file.py <device_ip>:updated_file.py
```

> **Security note:** MicroPython's WebREPL uses an unencrypted WebSocket (`ws://`). The OTA password is sent in plaintext over the network. This is acceptable on a trusted home network, but anyone able to observe local traffic during a push would see the password. Do not use this over an untrusted or public network.

Find the device IP in the serial output on boot, or check your router's DHCP table. After pushing all changed files, reset the device:
```
python webrepl_cli.py -p <OTA_PASSWORD> --reboot <device_ip>
```

---

## Serial output

Example output on a clear day:

```
=== ESP32 Rain Sensor booting ===
Status: None -> error
WiFi: connecting to MyNetwork...
WiFi: connected, IP=<device_ip>
OTA: WebREPL started on port 8266
Weather: recent rain (3h) = 0.000 in
Weather: forecast rain (12h) = 0.000 in
Irrigation: allowing — rain_3h=0.000" forecast_12h=0.000", relay de-energized
Status: error -> ok
```

Example output when rain is detected:

```
Weather: recent rain (3h) = 0.310 in
Weather: forecast rain (12h) = 0.120 in
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

# ESP32 Rain Sensor

MicroPython firmware for an ESP32-WROOM-32U that replaces the broken rain sensor on a Rain Bird ESP-ME sprinkler controller. Uses OpenWeatherMap to make irrigation decisions based on recent and forecast rainfall.

## Flashing MicroPython

1. **Download firmware:** `ESP32_GENERIC-20241129-v1.24.1.bin` from https://micropython.org/download/ESP32_GENERIC/
2. **Install esptool:** `pip install esptool`
3. **Erase flash:**
   ```
   esptool.py --chip esp32 --port COM<N> erase_flash
   ```
4. **Flash firmware:**
   ```
   esptool.py --chip esp32 --port COM<N> --baud 460800 write_flash -z 0x1000 ESP32_GENERIC-20241129-v1.24.1.bin
   ```

## Uploading project files

Use [mpremote](https://docs.micropython.org/en/latest/reference/mpremote.html):

```
pip install mpremote
```

Copy `secrets_template.py` to `secrets.py` and fill in your credentials, then upload all project files:

```
mpremote connect COM<N> cp boot.py main.py config.py network.py weather.py irrigation.py status.py ota.py secrets.py :
```

Open serial monitor at 115200 baud:
```
mpremote connect COM<N> repl
```

## Configuration

Edit `config.py` for tunable constants (thresholds, intervals, pins).  
Edit `secrets.py` (copied from `secrets_template.py`) for credentials — **never commit this file**.

## Rainfall thresholds

- Block irrigation if rain in last 3 hours > **0.25 inches** (`RAIN_THRESHOLD_3H`)
- Block irrigation if forecast rain in next 12 hours > **0.5 inches** (`RAIN_THRESHOLD_12H`)
- If the weather API is unreachable, irrigation is **allowed** (fail-open)

## LED status

| Pattern | Meaning |
|---------|---------|
| Solid on | Connected, irrigation allowed |
| Slow blink (~1s) | Connected, irrigation blocked (rain) |
| Fast blink (~250ms) | WiFi disconnected or API error |

## Wiring

Connect the relay's **NC (Normally Closed)** and **COM** terminals to the Rain Bird ESP-ME sensor terminals. The relay is de-energized by default, keeping the circuit closed so irrigation runs normally. The ESP32 energizes the relay to open the circuit and block irrigation.

Relay GPIO: **pin 22**

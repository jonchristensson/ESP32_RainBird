# Extensions

Possible next steps for this project, beyond the current Open-Meteo-only design.

## Background: the API can miss real rain

`weather.py`'s `rain_6h` comes from Open-Meteo's `past_hours` field, which is model/reanalysis output, not a gauge reading. In testing against this device's coordinates during an active thunderstorm, Open-Meteo reported `rain_6h=0.000"` for a 6-hour window in which the nearest NWS station (KICT) measured at least 0.4" actually falling. Convective (thunderstorm-cell) rain is the specific case where a forecast model's grid cell can miss what fell at one exact point, even though the model isn't "wrong" in a broader sense.

Cross-checking against `api.weather.gov` doesn't fully fix this either — it's still a point-source gauge (the nearest station can be miles away), and its hourly precip field also goes unreported/`null` during some active storm observations. See the research notes in this project's history for the full comparison.

The two options below both move the "did it actually rain here" question onto local hardware instead of any API, which is the pattern most mature smart-irrigation projects converge on (OpenSprinkler's PWS/rain-delay API hookup, Rachio's WeatherFlow Tempest integration, Home Assistant's `IrrigationEstimator` preferring real sensors over weather components).

---

## Option A — Commercial local weather station

Buy a standalone weather station with its own rain sensor, and have the ESP32 pull actual rainfall from its local API/feed instead of (or in addition to) Open-Meteo's past-precip field. All of these expose a local network API/feed with no subscription required for basic data access.

| Model | Price | Rain sensor | Notes |
|---|---|---|---|
| [WeatherFlow Tempest](https://tempest.earth/tempest-home-weather-system/) | ~$270–340 | Haptic (no moving parts) | All-in-one 7-sensor unit. [Open local API](https://weatherflow.github.io/Tempest/api/), no subscription. Direct [Rachio integration](https://rachio.com/products/weatherflow-tempest). Most-cited by hobbyists as the rain sensor that "actually works" for rain-skip automation. Caveat: documented under-reporting in very heavy rain and very light drizzle — worth checking against the 0.25"/0.5" thresholds this project uses. |
| [Ecowitt WS90](https://shop.ecowitt.com/products/ws90) | ~$150 (+ [GW3000](https://www.ecowitt.com/shop/goodsDetail/16) gateway ~$30–40 if needed) | Piezoelectric (no moving parts, no clogging) | 7-in-1 sensor array. |
| [Ecowitt WS69](https://shop.ecowitt.com/products/ws69) | ~$145 | Traditional tipping bucket | Same sensor suite as WS90 but the older mechanical bucket, which can clog with debris over time. |
| [Ambient Weather WS-2902 (Osprey)](https://ambientweather.com/ws-2902-smart-weather-station) | ~$160–200 | Traditional tipping bucket | Long track record, Wunderground-compatible local upload. |

**Tradeoffs:** higher cost, and you're paying for a full weather station (wind/UV/pressure/etc.) when only the rain gauge is needed. Integration would mean a second HTTPS client in the firmware (or a local push from the station) alongside/instead of the Open-Meteo call.

---

## Option B — DIY tipping-bucket rain gauge on the existing ESP32

Wire a bare tipping-bucket sensor directly to a GPIO pin on the ESP32 already running this firmware. Each bucket tip is a fixed volume of rain; count pulses via interrupt and multiply by the manufacturer's per-tip constant to get real accumulated rainfall for any window (e.g., replacing `rain_6h`).

| Part | Price | Notes |
|---|---|---|
| [Misol WH-SP-RG](https://www.robotics.org.za/WH-SP-RG) | ~$14–27 | Bare tipping-bucket mechanism with a reed switch — the same physical sensor used inside several of the Option A stations. ~0.3mm (~0.011") per tip. No gateway, no radio, no battery needed if wired directly to the ESP32. |

Reference builds for the pulse-counting approach:
- [DIY 3D Printed Rain Gauge Connects To Home Assistant (Hackaday)](https://hackaday.com/2023/05/30/diy-3d-printed-rain-gauge-connects-to-home-assistant/)
- [SS4H-RG Smart Rain Gauge — ESP32 + ESPHome](https://smartsolutions4home.com/ss4h-rg-rain-gauge/)
- [Rebuilding a rain gauge using ESP32 with live updates](https://garrysblog.com/2025/05/30/rebuilding-a-rain-gauge-using-esp32-with-live-updates/)
- [Home Assistant smart irrigation: local control, $25–89 hardware](https://botmonster.com/smart-home/smart-garden-irrigation-home-assistant-rain-sensor/)

These writeups mostly use ESPHome (which has a ready-made rain-gauge pulse-counter component). This project runs bare MicroPython, so the debounce/pulse-counting logic would need to be written directly — a GPIO interrupt handler incrementing a counter, read and reset each check cycle in place of (or alongside) the `weather.py` HTTPS call.

**Tradeoffs:** cheapest and most directly integrated option (no second network dependency, no cloud/API ambiguity), at the cost of writing and debugging the interrupt/debounce logic yourself, plus physical installation (mounting somewhere with clear sky, wiring back to the enclosure) that Option A's self-contained stations don't require.

---

## Not pursued: switching to `api.weather.gov` outright

Considered and set aside — it only covers the "actual past rain" half (still needs Open-Meteo or another source for the forecast side), the nearest station (KICT) can be several miles from the install site, its hourly precip field is frequently missing/`null` during active storms, and the GeoJSON response is heavier to parse on a memory-constrained device than either option above.

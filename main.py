import time
import wifi as net
import weather
import irrigation
import status
import ota
import config

print("=== ESP32 Rain Sensor booting ===")

status.set_status("error")   # fast-blink until first successful check

connected = net.connect()
if connected:
    import ntptime
    try:
        ntptime.settime()
        print("NTP: time synchronized")
    except Exception as e:
        print(f"NTP: sync failed — {e}")
    ota.start()

_last_check = 0
_ota_started = connected


def run_weather_cycle():
    global _last_check
    rain_3h, forecast_12h, success = weather.check_weather()
    action = irrigation.update(rain_3h, forecast_12h, success)

    if not success:
        status.set_status("error")
    elif action == "blocked":
        status.set_status("rain")
    else:
        status.set_status("ok")

    _last_check = time.time()


# Check immediately on boot (if WiFi is up)
if connected:
    run_weather_cycle()

while True:
    time.sleep(10)

    connected = net.tick()   # handles reconnect + watchdog

    if not connected:
        irrigation.allow()
        status.set_status("error")
        continue

    # Start OTA the first time we get a connection (handles boot with no WiFi)
    if not _ota_started:
        ota.start()
        _ota_started = True

    now = time.time()
    if now - _last_check >= config.CHECK_INTERVAL_S:
        run_weather_cycle()

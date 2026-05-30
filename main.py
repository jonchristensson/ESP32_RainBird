import time
import network as net
import weather
import irrigation
import status
import config

print("=== ESP32 Rain Sensor booting ===")

status.set_status("error")   # fast-blink until first successful check

net.connect()

_last_check = 0


def run_weather_cycle():
    global _last_check
    if not net.is_connected():
        print("Main: WiFi not connected, skipping weather check — fail-open")
        irrigation.allow()
        status.set_status("error")
        return

    rain_3h, forecast_12h, success = weather.check_weather()
    action = irrigation.update(rain_3h, forecast_12h, success)

    if not success:
        status.set_status("error")
    elif action == "blocked":
        status.set_status("rain")
    else:
        status.set_status("ok")

    _last_check = time.time()


# Check immediately on boot
run_weather_cycle()

while True:
    time.sleep(10)
    now = time.time()
    if now - _last_check >= config.CHECK_INTERVAL_S:
        run_weather_cycle()

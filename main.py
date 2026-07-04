import gc
import time
import wifi as net
import weather
import irrigation
import status
import ota
import config
import reset_tracker
import logger

print("=== ESP32 Rain Sensor booting ===")

if reset_tracker.is_boot_looping():
    import machine
    cause = machine.reset_cause()
    print(f"=== SAFE MODE: {reset_tracker.count} rapid resets, cause={cause} — awaiting OTA repair ===")
    irrigation.allow()
    status.set_status("safe")
    if net.connect():
        ota.start()
    while True:
        time.sleep(10)

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
_boot_time = time.time()
_counter_cleared = False


def run_weather_cycle(event="check"):
    global _last_check
    rain_6h, forecast_12h, success = weather.check_weather()
    action = irrigation.update(rain_6h, forecast_12h, success)

    if not success:
        status.set_status("error")
    elif action == "blocked":
        status.set_status("rain")
    else:
        status.set_status("ok")

    _last_check = time.time()

    block_reason = None
    if action == "blocked":
        parts = []
        if rain_6h > config.RAIN_THRESHOLD_6H:
            parts.append(f"rain {rain_6h:.3f}\"")
        if forecast_12h > config.RAIN_THRESHOLD_12H:
            parts.append(f"forecast {forecast_12h:.3f}\"")
        block_reason = ", ".join(parts) if parts else "threshold exceeded"

    logger.log(event, rain_6h, forecast_12h, action, block_reason, success)
    gc.collect()


# Check immediately on boot (if WiFi is up)
if connected:
    run_weather_cycle("boot")

while True:
    time.sleep(10)

    if not _counter_cleared and (time.time() - _boot_time) >= 60:
        reset_tracker.clear_counter()
        _counter_cleared = True

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

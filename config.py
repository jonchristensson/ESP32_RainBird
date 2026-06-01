from secrets import (
    WIFI_SSID,
    WIFI_PASSWORD,
    LATITUDE,
    LONGITUDE,
    OTA_PASSWORD,
)

# Rainfall thresholds (inches)
RAIN_THRESHOLD_6H = 0.25    # block if recent 6h rain exceeds this
RAIN_THRESHOLD_12H = 0.5    # block if 12h forecast exceeds this

# Timing
CHECK_INTERVAL_S = 900      # weather check interval (15 minutes)
WIFI_TIMEOUT_S = 30         # max seconds to wait for initial WiFi connection
WIFI_RECONNECT_INTERVAL_S = 30   # seconds between reconnect attempts
WIFI_WATCHDOG_TIMEOUT_S = 300    # reboot after this many seconds disconnected

# GPIO pins
RELAY_PIN = 22
LED_PIN = 2                 # onboard LED on most ESP32-WROOM-32 boards

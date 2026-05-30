import network
import time
import config

_wlan = network.WLAN(network.STA_IF)


def connect() -> bool:
    """Attempt initial WiFi connection. Returns True if connected."""
    _wlan.active(True)
    if _wlan.isconnected():
        return True

    print(f"WiFi: connecting to {config.WIFI_SSID}...")
    _wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)

    deadline = time.time() + config.WIFI_TIMEOUT_S
    while not _wlan.isconnected():
        if time.time() >= deadline:
            print("WiFi: connection timed out")
            return False
        time.sleep(0.5)

    print(f"WiFi: connected, IP={_wlan.ifconfig()[0]}")
    return True


def is_connected() -> bool:
    return _wlan.isconnected()


def ip_address() -> str:
    return _wlan.ifconfig()[0] if _wlan.isconnected() else ""

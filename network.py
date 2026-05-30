import network
import time
import machine
import config

_wlan = network.WLAN(network.STA_IF)
_disconnect_since = None    # epoch when WiFi first dropped (None = connected)
_last_attempt = 0           # epoch of last reconnect attempt


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


def tick() -> bool:
    """
    Call every ~10s from the main loop.
    - If connected: clears disconnect state and returns True.
    - If disconnected: attempts reconnect every WIFI_RECONNECT_INTERVAL_S seconds.
    - Reboots after WIFI_WATCHDOG_TIMEOUT_S seconds of continuous disconnection.
    Returns True if connected.
    """
    global _disconnect_since, _last_attempt

    if _wlan.isconnected():
        if _disconnect_since is not None:
            print("WiFi: reconnected")
            _disconnect_since = None
        return True

    now = time.time()

    if _disconnect_since is None:
        _disconnect_since = now
        _last_attempt = 0
        print("WiFi: connection lost, starting reconnect loop")

    elapsed = now - _disconnect_since

    if elapsed >= config.WIFI_WATCHDOG_TIMEOUT_S:
        print(f"WiFi: down for {int(elapsed)}s — rebooting to clear network stack")
        time.sleep(1)
        machine.reset()

    if now - _last_attempt >= config.WIFI_RECONNECT_INTERVAL_S:
        attempt_num = int(elapsed / config.WIFI_RECONNECT_INTERVAL_S) + 1
        print(f"WiFi: reconnect attempt {attempt_num} ({int(elapsed)}s since drop)...")
        _last_attempt = now
        _wlan.disconnect()
        time.sleep(1)
        _wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
        deadline = time.time() + 10
        while not _wlan.isconnected() and time.time() < deadline:
            time.sleep(0.5)
        if _wlan.isconnected():
            print(f"WiFi: reconnected after {int(elapsed)}s, IP={_wlan.ifconfig()[0]}")
            _disconnect_since = None
            return True
        print("WiFi: reconnect attempt failed")

    return False

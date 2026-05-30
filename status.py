from machine import Pin, Timer
import config

_led = Pin(config.LED_PIN, Pin.OUT, value=0)
_timer = Timer(0)
_current_state = None

# Blink periods in ms (half-period — each timer tick toggles the LED)
_PERIODS = {
    "ok":    None,    # solid on, no timer needed
    "rain":  500,     # 1s cycle → toggle every 500ms
    "error": 125,     # 250ms cycle → toggle every 125ms
}


def _stop_timer():
    _timer.deinit()


def set_status(state: str) -> None:
    global _current_state
    if state == _current_state:
        return

    prev = _current_state
    _current_state = state
    _stop_timer()

    if state == "ok":
        _led.value(1)
    elif state == "rain":
        _led.value(1)
        _timer.init(period=_PERIODS["rain"], mode=Timer.PERIODIC,
                    callback=lambda t: _led.value(not _led.value()))
    elif state == "error":
        _led.value(0)
        _timer.init(period=_PERIODS["error"], mode=Timer.PERIODIC,
                    callback=lambda t: _led.value(not _led.value()))
    else:
        _led.value(0)

    print(f"Status: {prev} -> {state}")

from machine import Pin
import config

_relay = Pin(config.RELAY_PIN, Pin.OUT, value=0)   # de-energized (fail-open) on init


def update(rain_6h: float, forecast_12h: float, success: bool) -> str:
    if not success:
        _relay.value(0)
        print("Irrigation: API failed — fail-open, relay de-energized (irrigation ALLOWED)")
        return "allowed"

    reasons = []
    if rain_6h > config.RAIN_THRESHOLD_6H:
        reasons.append(f"recent rain {rain_6h:.3f}\" > {config.RAIN_THRESHOLD_6H}\"")
    if forecast_12h > config.RAIN_THRESHOLD_12H:
        reasons.append(f"forecast {forecast_12h:.3f}\" > {config.RAIN_THRESHOLD_12H}\"")

    if reasons:
        _relay.value(1)
        print(f"Irrigation: BLOCKING — {', '.join(reasons)}, relay energized")
        return "blocked"
    else:
        _relay.value(0)
        print(
            f"Irrigation: allowing — rain_6h={rain_6h:.3f}\" "
            f"forecast_12h={forecast_12h:.3f}\", relay de-energized"
        )
        return "allowed"


def allow():
    """Force relay de-energized (fail-open). Called on WiFi loss."""
    _relay.value(0)

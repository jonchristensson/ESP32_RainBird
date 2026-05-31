import json as ujson
import ssl as ussl
import socket as usocket
import config

_HOST = "api.openweathermap.org"
_CURRENT_PATH = "/data/2.5/weather"
_FORECAST_PATH = "/data/2.5/forecast"

with open("owm_ca.pem", "r") as _f:
    _CA_CERT = _f.read()


def _https_get(path: str, params: dict) -> tuple:
    """
    Minimal HTTPS GET using raw sockets + ussl with cert verification.
    Returns (status_code: int, body: str) or raises on connection failure.
    """
    query = "&".join(f"{k}={v}" for k, v in params.items())
    request = (
        f"GET {path}?{query} HTTP/1.0\r\n"
        f"Host: {_HOST}\r\n"
        f"Connection: close\r\n\r\n"
    )

    addr = usocket.getaddrinfo(_HOST, 443, 0, usocket.SOCK_STREAM)[0][-1]
    sock = usocket.socket()
    sock.settimeout(15)
    try:
        sock.connect(addr)
        wrapped = ussl.wrap_socket(
            sock,
            server_hostname=_HOST,
            cert_reqs=ussl.CERT_REQUIRED,
            cadata=_CA_CERT,
        )
        wrapped.write(request.encode())
        response = b""
        while True:
            chunk = wrapped.read(1024)
            if not chunk:
                break
            response += chunk
    finally:
        sock.close()

    response = response.decode("utf-8")
    header, _, body = response.partition("\r\n\r\n")
    status_line = header.split("\r\n")[0]
    status_code = int(status_line.split(" ")[1])
    return status_code, body


def _base_params() -> dict:
    return {
        "lat": config.LATITUDE,
        "lon": config.LONGITUDE,
        "appid": config.OWM_API_KEY,
        "units": "imperial",
    }


def check_weather() -> tuple:
    """
    Fetch current weather and 12h forecast from OpenWeatherMap.
    Returns (rain_3h: float, forecast_12h: float, success: bool).
    On any error returns (0.0, 0.0, False).
    """
    rain_3h = 0.0
    forecast_12h = 0.0

    try:
        # --- Current weather ---
        status, body = _https_get(_CURRENT_PATH, _base_params())
        if status != 200:
            print(f"Weather: current endpoint returned HTTP {status}")
            return 0.0, 0.0, False

        data = ujson.loads(body)
        if "rain" in data:
            rain_mm = data["rain"].get("1h", data["rain"].get("3h", 0.0))
            rain_3h = float(rain_mm) / 25.4  # mm → inches
        print(f"Weather: recent rain = {rain_3h:.3f} in")

        # --- Forecast ---
        status, body = _https_get(_FORECAST_PATH, _base_params())
        if status != 200:
            print(f"Weather: forecast endpoint returned HTTP {status}")
            return rain_3h, 0.0, False

        data = ujson.loads(body)
        blocks = data.get("list", [])[:4]   # first 4 × 3h blocks = 12h
        for block in blocks:
            forecast_12h += float(block.get("rain", {}).get("3h", 0.0)) / 25.4  # mm → inches
        print(f"Weather: forecast rain (12h) = {forecast_12h:.3f} in")

        return rain_3h, forecast_12h, True

    except OSError as e:
        print(f"Weather: network error — {e}")
    except ValueError as e:
        print(f"Weather: JSON parse error — {e}")
    except Exception as e:
        print(f"Weather: unexpected error — {e}")

    return 0.0, 0.0, False

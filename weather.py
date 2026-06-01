import json as ujson
import ssl as ussl
import socket as usocket
import config

_HOST = "api.open-meteo.com"
_PATH = "/v1/forecast"

with open("ca.pem", "r") as _f:
    _CA_CERT = _f.read()


def _https_get(path: str, query: str) -> tuple:
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


def check_weather() -> tuple:
    rain_6h = 0.0
    forecast_12h = 0.0

    try:
        query = (
            f"latitude={config.LATITUDE}&longitude={config.LONGITUDE}"
            "&hourly=precipitation&precipitation_unit=inch"
            "&past_hours=6&forecast_hours=12"
        )
        status, body = _https_get(_PATH, query)
        if status != 200:
            print(f"Weather: endpoint returned HTTP {status}")
            return 0.0, 0.0, False

        data = ujson.loads(body)
        precip = data["hourly"]["precipitation"]

        rain_6h = sum(precip[:6])
        forecast_12h = sum(precip[6:])

        print(f"Weather: rain_6h={rain_6h:.3f}\" forecast_12h={forecast_12h:.3f}\"")
        return rain_6h, forecast_12h, True

    except OSError as e:
        print(f"Weather: network error — {e}")
    except ValueError as e:
        print(f"Weather: JSON parse error — {e}")
    except Exception as e:
        print(f"Weather: unexpected error — {e}")

    return 0.0, 0.0, False

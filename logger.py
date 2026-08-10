import gc
import json
import ssl as ussl
import socket as usocket
import network
import time
import config

_CERT_FILE = "google_ca.pem"
_TIMEOUT = 15
_MAX_RESPONSE = 8192


def _parse_url(url):
    url = url.replace("https://", "")
    host, _, path = url.partition("/")
    return host, ("/" + path) if path else "/"


def _https_post(host, path, body_bytes, ca_cert):
    request = (
        f"POST {path} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(body_bytes)}\r\n"
        f"Connection: close\r\n\r\n"
    ).encode() + body_bytes

    addr = usocket.getaddrinfo(host, 443, 0, usocket.SOCK_STREAM)[0][-1]
    sock = usocket.socket()
    sock.settimeout(_TIMEOUT)
    wrapped = None
    try:
        sock.connect(addr)
        wrapped = ussl.wrap_socket(
            sock,
            server_hostname=host,
            cert_reqs=ussl.CERT_REQUIRED,
            cadata=ca_cert,
        )
        wrapped.write(request)
        response = b""
        while True:
            chunk = wrapped.read(1024)
            if not chunk:
                break
            response += chunk
            if len(response) > _MAX_RESPONSE:
                break
    finally:
        if wrapped is not None:
            wrapped.close()
        else:
            sock.close()
        gc.collect()

    text = response.decode("utf-8")
    header, _, body = text.partition("\r\n\r\n")
    status_line = header.split("\r\n")[0]
    status_code = int(status_line.split(" ")[1])

    return status_code, body


def log(event, rain_6h, forecast_12h, decision, block_reason, api_success):
    if "YOUR_DEPLOYMENT_ID" in config.GOOGLE_SHEETS_URL:
        print("Logger: Google Sheets not configured, skipping")
        return

    try:
        wlan = network.WLAN(network.STA_IF)
        rssi = wlan.status("rssi") if wlan.isconnected() else 0
        free_mem = gc.mem_free()

        payload = json.dumps({
            "event": event,
            "rain_6h": rain_6h,
            "forecast_12h": forecast_12h,
            "decision": decision,
            "block_reason": block_reason,
            "api_success": api_success,
            "wifi_rssi": rssi,
            "free_memory": free_mem,
            "device_time": time.time(),
        }).encode()

        host, path = _parse_url(config.GOOGLE_SHEETS_URL)

        with open(_CERT_FILE, "r") as f:
            ca_cert = f.read()

        status, _ = _https_post(host, path, payload, ca_cert)
        if status in (200, 302):
            print(f"Logger: {event} logged OK")
        else:
            print(f"Logger: server returned {status}")
    except Exception as e:
        print(f"Logger: failed — {e}")

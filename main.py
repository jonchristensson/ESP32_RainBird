import time
import network as net

print("=== ESP32 Rain Sensor booting ===")

connected = net.connect()
if not connected:
    print("WiFi: failed to connect on boot — will retry in main loop")

# Placeholder main loop — subsequent issues fill this in
while True:
    if net.is_connected():
        print(f"WiFi: OK, IP={net.ip_address()}")
    else:
        print("WiFi: not connected")
    time.sleep(30)

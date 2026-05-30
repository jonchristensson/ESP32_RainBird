import network as net_module

# Disable AP interface — only STA mode needed
ap = net_module.WLAN(net_module.AP_IF)
ap.active(False)

# WebREPL (OTA) is started from main.py after WiFi connects so the password
# from secrets.py is available and the network stack is ready.

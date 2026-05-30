import network as net_module

# Disable AP interface on boot — only STA mode needed
ap = net_module.WLAN(net_module.AP_IF)
ap.active(False)

import sys, json, urllib.request

sys.path.insert(0, ".")
from secrets import LATITUDE, LONGITUDE

URL = (
    "https://api.open-meteo.com/v1/forecast"
    f"?latitude={LATITUDE}&longitude={LONGITUDE}"
    "&hourly=precipitation&precipitation_unit=inch"
    "&past_hours=6&forecast_hours=12"
)

print(f"GET {URL}\n")
with urllib.request.urlopen(URL) as r:
    data = json.loads(r.read())

print("=== Raw JSON ===")
print(json.dumps(data, indent=2))

times = data["hourly"]["time"]
precip = data["hourly"]["precipitation"]

rain_6h = sum(precip[:6])
forecast_12h = sum(precip[6:])

print(f"\nrain_6h     = {rain_6h:.3f} in  (past 6 hours)")
print(f"forecast_12h = {forecast_12h:.3f} in  (next 12 hours)")

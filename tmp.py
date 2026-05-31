import sys, urllib.request, json

sys.path.insert(0, ".")
from secrets import OWM_API_KEY, LATITUDE, LONGITUDE

BASE = "https://api.openweathermap.org/data/2.5"
PARAMS = f"lat={LATITUDE}&lon={LONGITUDE}&appid={OWM_API_KEY}&units=imperial"

def fetch(path):
    with urllib.request.urlopen(f"{BASE}{path}?{PARAMS}") as r:
        return json.loads(r.read())

print("=== Current weather (raw JSON) ===")
current = fetch("/weather")
print(json.dumps(current, indent=2))

print("\n=== Forecast first 4 blocks (raw JSON) ===")
forecast = fetch("/forecast")
print(json.dumps({"list": forecast["list"][:4]}, indent=2))

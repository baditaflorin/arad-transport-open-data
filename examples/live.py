"""Python 3.10+, standard library only. Read once; no credentials."""
import json
import urllib.request
from datetime import datetime, timezone

LIVE_BASE = "https://www.telelink.city/api/v1/e39aa927-11c1-435f-92b9-57804f7bc1b4/transport"
DATA_BASE = "https://baditaflorin.github.io/arad-transport-open-data/data"


def get_json(url):
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def main():
    routes = {r["id"]: r for r in get_json(DATA_BASE + "/routes.json")}
    for vehicle in get_json(LIVE_BASE + "/planner/vehicles"):
        updated = datetime.fromisoformat(vehicle["lastUpdated"].replace("Z", "+00:00"))
        route = routes.get(vehicle["routeId"], {})
        print(json.dumps({
            "line": route.get("shortName"), "mode": route.get("mode"),
            "vehicleId": vehicle["vehicleId"], "latitude": vehicle["latitude"],
            "longitude": vehicle["longitude"], "lastUpdated": vehicle["lastUpdated"],
            "stale": (datetime.now(timezone.utc) - updated).total_seconds() > 120,
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Export the public Arad planner API. Python standard library only."""

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone

SOURCE = "https://arad-transport.telelink.city"
SETTINGS_URL = SOURCE + "/wp-content/plugins/planner/data/settings.json"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "docs/data"


def decode_polyline(encoded):
    """Google encoded polyline, precision 5, returned as GeoJSON lon/lat."""
    pos, lat, lon, points = 0, 0, 0, []
    while pos < len(encoded):
        values = []
        for _ in range(2):
            value, shift = 0, 0
            while True:
                if pos >= len(encoded):
                    raise ValueError("Truncated polyline")
                byte = ord(encoded[pos]) - 63
                pos += 1
                if not 0 <= byte <= 63 or shift > 30:
                    raise ValueError("Invalid polyline")
                value |= (byte & 31) << shift
                shift += 5
                if byte < 32:
                    break
            values.append(~(value >> 1) if value & 1 else value >> 1)
        lat += values[0]
        lon += values[1]
        points.append([lon / 1e5, lat / 1e5])
    return points


class Client:
    def __init__(self, timeout=45, interval=0.5):
        self.timeout = timeout
        self.interval = interval
        self.last_request = 0
        self.receipts = []

    def get(self, url):
        for attempt in range(3):
            time.sleep(max(0, self.interval - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            request = urllib.request.Request(url, headers={
                "User-Agent": "AradTransportOpenData/1.0 (+https://github.com/baditaflorin/arad-transport-open-data)",
                "Origin": SOURCE,
                "Accept": "application/json",
            })
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    body = response.read()
                    data = json.loads(body)
                    self.receipts.append({
                        "url": url, "fetchedAt": datetime.now(timezone.utc).isoformat(),
                        "httpStatus": response.status, "sha256": hashlib.sha256(body).hexdigest(),
                        "bytes": len(body), "serverDate": response.headers.get("Date"),
                    })
                    return data
            except urllib.error.HTTPError as error:
                if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                    raise
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                reason = getattr(error, "reason", error)
                if getattr(reason, "errno", None) == 49 or attempt == 2:
                    raise
            time.sleep(2 ** (attempt + 1))
        raise RuntimeError("Unreachable")


def normalize(routes, stops):
    normalized_routes, patterns, route_stops = [], [], []
    stop_ids = {stop["id"] for stop in stops}
    for route in routes:
        normalized_routes.append({
            **{key: value for key, value in route.items() if key != "patterns"},
            "mode": {0: "tram", 3: "bus"}.get(route["type"], "other"),
            "patternCount": len(route["patterns"]),
            "sourceUrl": f"{SOURCE}/app/lines/route/{route['id']}",
        })
        for pattern in route["patterns"]:
            missing = set(pattern["stops"]) - stop_ids
            if missing:
                raise ValueError(f"Unknown stops in route {route['id']}: {missing}")
            pattern_id = f"{route['id']}:{pattern['index']}"
            patterns.append({
                **{key: value for key, value in pattern.items() if key not in ("stops", "geometry")},
                "patternId": pattern_id, "stopIds": pattern["stops"],
                "stopCount": len(pattern["stops"]), "encodedPolyline": pattern["geometry"],
            })
            for sequence, stop_id in enumerate(pattern["stops"], 1):
                route_stops.append({
                    "routeId": route["id"], "patternId": pattern_id,
                    "patternIndex": pattern["index"], "stopSequence": sequence, "stopId": stop_id,
                })
    normalized_stops = [{
        **stop, "routeIds": sorted({p["routeId"] for p in stop["patterns"]}),
        "sourceUrl": f"{SOURCE}/app/lines/stop/{stop['id']}",
    } for stop in stops]
    return normalized_routes, patterns, route_stops, normalized_stops


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict))
                             else value for key, value in row.items()})


def feature_collection(features):
    return {"type": "FeatureCollection", "features": features}


def point_feature(row, id_key):
    return {"type": "Feature", "id": row[id_key],
            "geometry": {"type": "Point", "coordinates": [row["longitude"], row["latitude"]]},
            "properties": {key: value for key, value in row.items() if key not in ("latitude", "longitude", "patterns")}}


def export(output, timeout=45, include_arrivals=False, interval=0.5):
    client = Client(timeout, interval)
    settings = client.get(SETTINGS_URL)
    api_base = f"{settings['app']['apiUrl'].rstrip('/')}/{settings['app']['tenantId']}/transport"
    raw = {name: client.get(api_base + "/" + endpoint) for name, endpoint in {
        "routes": "planner/routes", "stops": "planner/stops", "vehicles": "planner/vehicles",
        "alerts": "gtfsrt/alerts?mediaType=WebPortal",
    }.items()}
    if not isinstance(raw["routes"], list) or not raw["routes"] or not raw["stops"]:
        raise ValueError("Empty or invalid upstream dataset; retaining previous export")
    routes, patterns, route_stops, stops = normalize(raw["routes"], raw["stops"])
    arrivals = []
    if include_arrivals:
        for index, stop in enumerate(stops, 1):
            groups = client.get(api_base + f"/planner/stops/{stop['id']}/times")
            for group in groups:
                for arrival in group["times"]:
                    arrivals.append({"routeId": group["route"]["routeId"],
                                     "patternIndex": group["route"]["index"], **arrival})
            if index % 25 == 0 or index == len(stops):
                print(f"Arrivals: {index}/{len(stops)} stops", flush=True)
    fetched_at = datetime.now(timezone.utc).isoformat()
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".arad-export-", dir=output.parent))
    try:
        (stage / "raw").mkdir()
        for name, data in raw.items():
            write_json(stage / "raw" / f"{name}.json", data)
        datasets = {"routes": routes, "patterns": patterns, "routeStops": route_stops,
                    "stops": stops, "vehiclesSnapshot": raw["vehicles"], "arrivalsSnapshot": arrivals}
        for name, data in datasets.items():
            write_json(stage / f"{name}.json", data)
        columns = {
            "routes": ["id", "shortName", "longName", "type", "mode", "color", "textColor", "patternCount", "inbound", "outbound", "sourceUrl"],
            "patterns": ["patternId", "routeId", "index", "direction", "fromStopId", "toStopId", "viaStopId", "stopCount", "stopIds", "encodedPolyline", "patternHash"],
            "routeStops": ["routeId", "patternId", "patternIndex", "stopSequence", "stopId"],
            "stops": ["id", "code", "name", "latitude", "longitude", "wheelchairBoarding", "routeIds", "sourceUrl"],
            "vehiclesSnapshot": ["vehicleId", "label", "routeId", "patternIndex", "tripId", "headsign", "latitude", "longitude", "heading", "speed", "delaySeconds", "nextStopArrival", "lastUpdated", "stopId", "stopStatus"],
            "arrivalsSnapshot": ["stopId", "routeId", "patternIndex", "tripId", "scheduledArrival", "scheduledDeparture", "arrivalDelay", "departureDelay", "realtime", "wheelchairAccessible", "bikesAllowed"],
        }
        for name, fields in columns.items():
            write_csv(stage / f"{name}.csv", datasets[name], fields)
        write_json(stage / "stops.geojson", feature_collection([point_feature(s, "id") for s in stops]))
        write_json(stage / "vehiclesSnapshot.geojson", feature_collection([point_feature(v, "vehicleId") for v in raw["vehicles"]]))
        route_by_id = {route["id"]: route for route in routes}
        write_json(stage / "routes.geojson", feature_collection([{
            "type": "Feature", "id": p["patternId"],
            "geometry": {"type": "LineString", "coordinates": decode_polyline(p["encodedPolyline"])},
            "properties": {**{k: v for k, v in p.items() if k not in ("stopIds", "encodedPolyline")},
                           "shortName": route_by_id[p["routeId"]]["shortName"],
                           "mode": route_by_id[p["routeId"]]["mode"],
                           "color": route_by_id[p["routeId"]].get("color", "cc2513")},
        } for p in patterns]))
        manifest = {
            "schemaVersion": "1.0.0", "fetchedAt": fetched_at, "timezone": "Europe/Bucharest",
            "sourceUrl": SOURCE, "settingsUrl": SETTINGS_URL, "apiBaseUrl": api_base,
            "endpoints": {"routes": api_base + "/planner/routes", "stops": api_base + "/planner/stops",
                          "vehicles": api_base + "/planner/vehicles", "routeVehicles": api_base + "/planner/vehicles/route/{routeId}",
                          "stopTimes": api_base + "/planner/stops/{stopId}/times", "alerts": api_base + "/gtfsrt/alerts?mediaType=WebPortal"},
            "counts": {**{k: len(v) for k, v in datasets.items()}, "tramRoutes": sum(r["type"] == 0 for r in routes),
                       "busRoutes": sum(r["type"] == 3 for r in routes)},
            "arrivalsIncluded": include_arrivals,
            "coverage": "All routes and stops returned by the public web planner; not independently verified against the full CTP network.",
            "dataLicense": "No explicit upstream data reuse license identified. Source attribution is retained. MIT covers project code only.",
            "notes": ["Snapshot files do not update live.", "Arrivals are an upcoming-departure window, not a complete weekly timetable.",
                      "Route type 0 = tram, 3 = bus (GTFS codes). Pattern index and direction are preserved, including negative values.",
                      "GeoJSON uses WGS84 longitude, latitude. CSV is UTF-8 with BOM. speed is preserved without assuming its undocumented unit."],
            "requests": client.receipts,
            "files": {p.name: {"bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                      for p in sorted(stage.iterdir()) if p.is_file()},
        }
        write_json(stage / "manifest.json", manifest)
        with zipfile.ZipFile(stage / "arad-transport.zip", "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(stage.rglob("*")):
                if path.is_file() and path.suffix != ".zip":
                    archive.write(path, path.relative_to(stage))
        output.mkdir(exist_ok=True)
        for path in stage.iterdir():
            destination = output / path.name
            if path.is_dir():
                shutil.copytree(path, destination, dirs_exist_ok=True)
            else:
                os.replace(path, destination)
        print(json.dumps(manifest["counts"], ensure_ascii=False))
        return manifest
    finally:
        shutil.rmtree(stage)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=float(os.getenv("ARAD_HTTP_TIMEOUT", "45")))
    parser.add_argument("--request-interval", type=float, default=0.5, help="Minimum seconds between upstream requests")
    parser.add_argument("--include-arrivals", action="store_true", help="Fetch the upcoming departure window for every stop")
    args = parser.parse_args()
    if args.timeout <= 0 or args.request_interval < 0.5:
        parser.error("timeout must be positive and request-interval must be at least 0.5 seconds")
    export(args.output, args.timeout, args.include_arrivals, args.request_interval)


if __name__ == "__main__":
    main()

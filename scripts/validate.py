#!/usr/bin/env python3
"""Offline integrity check for the published kit. No upstream requests."""
import csv
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs/data"


def validate():
    manifest = json.loads((DATA / "manifest.json").read_text())
    datasets = {name: json.loads((DATA / f"{name}.json").read_text()) for name in (
        "routes", "patterns", "routeStops", "stops", "vehiclesSnapshot", "arrivalsSnapshot")}
    for name, rows in datasets.items():
        assert len(rows) == manifest["counts"][name], f"Count mismatch: {name}"
        with (DATA / f"{name}.csv").open(encoding="utf-8-sig", newline="") as handle:
            csv_rows = list(csv.DictReader(handle))
        assert len(csv_rows) == len(rows), f"CSV count mismatch: {name}"
        for original, flattened in zip(rows, csv_rows):
            for key, cell in flattened.items():
                value = original.get(key)
                expected = json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else "" if value is None else str(value)
                assert cell == expected, f"CSV value mismatch: {name}.{key}"
    route_ids = {r["id"] for r in datasets["routes"]}
    stop_ids = {s["id"] for s in datasets["stops"]}
    pattern_ids = {p["patternId"] for p in datasets["patterns"]}
    assert len(route_ids) == len(datasets["routes"])
    assert len(stop_ids) == len(datasets["stops"])
    assert len(pattern_ids) == len(datasets["patterns"])
    for pattern in datasets["patterns"]:
        assert pattern["routeId"] in route_ids
        assert pattern["stopCount"] == len(pattern["stopIds"])
        assert set(pattern["stopIds"]) <= stop_ids
        ordered = [r for r in datasets["routeStops"] if r["patternId"] == pattern["patternId"]]
        assert [r["stopId"] for r in ordered] == pattern["stopIds"]
        assert [r["stopSequence"] for r in ordered] == list(range(1, len(ordered) + 1))
    for stop in datasets["stops"]:
        assert -90 <= stop["latitude"] <= 90 and -180 <= stop["longitude"] <= 180
        assert set(stop["routeIds"]) <= route_ids
    for name in ("routes", "stops", "vehiclesSnapshot"):
        geo = json.loads((DATA / f"{name}.geojson").read_text())
        assert geo["type"] == "FeatureCollection"
        expected = len(datasets["patterns" if name == "routes" else name])
        assert len(geo["features"]) == expected
        for feature in geo["features"]:
            points = feature["geometry"]["coordinates"]
            if feature["geometry"]["type"] == "Point":
                points = [points]
            else:
                assert len(points) >= 2
            for lon, lat in points:
                assert 20 < lon < 23 and 45 < lat < 48, "Geometry outside Arad region / swapped coordinates"
    for name, receipt in manifest["files"].items():
        path = DATA / name
        assert path.stat().st_size == receipt["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == receipt["sha256"]
    with zipfile.ZipFile(DATA / "arad-transport.zip") as archive:
        assert archive.testzip() is None
        assert "manifest.json" in archive.namelist()
        assert "routes.json" in archive.namelist()
    schema = json.loads((ROOT / "docs/schema.json").read_text())
    spec = json.loads((ROOT / "docs/openapi.json").read_text())
    assert spec["openapi"] == "3.1.0" and len(spec["paths"]) >= 7
    assert "Vehicle" in schema["$defs"] and "Route" in schema["$defs"]
    # These files are public: catch accidental copied credentials before publishing.
    secret_pattern = re.compile(r"ak_[0-9a-f]{24,}|gh[pousr]_[A-Za-z0-9]{20,}|api_key=[^\s&\"']+", re.I)
    for path in (ROOT / "docs").rglob("*"):
        if path.is_file() and path.suffix in (".html", ".json", ".txt", ".csv", ".js"):
            assert not secret_pattern.search(path.read_text(encoding="utf-8-sig")), f"Possible credential: {path}"
    print("Validated counts, CSV parity, IDs, stop order, geometry, SHA-256, ZIP, API contracts and public-file secret scan.")


if __name__ == "__main__":
    validate()

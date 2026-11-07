#!/usr/bin/env python3
"""Publish machine-readable contracts for the observed public API and exports."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SITE = "https://baditaflorin.github.io/arad-transport-open-data"
LIVE = "https://www.telelink.city/api/v1/e39aa927-11c1-435f-92b9-57804f7bc1b4/transport"
INTEGER = {"type": "integer"}
STRING = {"type": "string"}
NUMBER = {"type": "number"}
DATE = {"type": "string", "format": "date-time"}


def array(items):
    return {"type": "array", "items": items}


def ref(name):
    return {"$ref": "#/$defs/" + name}


def obj(properties, required=(), description=None):
    result = {"type": "object", "properties": properties, "required": list(required), "additionalProperties": True}
    if description:
        result["description"] = description
    return result


def main():
    raw_pattern_properties = {
        "routeId": INTEGER, "index": {"type": "integer", "description": "May be negative; scoped to routeId."},
        "direction": {"type": "integer", "description": "Preserved from source; -1 is possible. Do not infer outbound/inbound."},
        "fromStopId": INTEGER, "toStopId": INTEGER, "viaStopId": {"type": ["integer", "null"]},
        "patternHash": STRING,
    }
    raw_route_properties = {
        "id": INTEGER, "shortName": STRING, "longName": STRING,
        "type": {"type": "integer", "description": "GTFS route type: 0 tram, 3 bus."},
        "color": {"type": ["string", "null"]}, "textColor": {"type": ["string", "null"]},
        "inbound": {"type": ["string", "null"]}, "outbound": {"type": ["string", "null"]},
    }
    raw_stop_properties = {
        "id": INTEGER, "code": {"type": ["string", "null"]}, "name": STRING,
        "latitude": {"type": "number", "minimum": -90, "maximum": 90},
        "longitude": {"type": "number", "minimum": -180, "maximum": 180},
        "wheelchairBoarding": {"type": "integer", "description": "GTFS enum: 0 unknown, 1 possible, 2 not possible. Preserve source value."},
        "patterns": array(obj({k: v for k, v in raw_pattern_properties.items() if k != "patternHash"})),
    }
    vehicle_properties = {
        "vehicleId": {"type": "string", "description": "Opaque ID; keep as string."}, "label": STRING,
        "routeId": {"type": "integer", "description": "Join to route.id, never to shortName."},
        "patternIndex": {"type": "integer", "description": "Join to pattern.index together with routeId. Can be negative."},
        "tripId": STRING, "headsign": {"type": ["string", "null"]},
        "latitude": raw_stop_properties["latitude"], "longitude": raw_stop_properties["longitude"],
        "lastUpdated": {**DATE, "description": "Position time in UTC. Demo considers age >120s stale."},
        "heading": NUMBER, "speed": {"type": ["number", "null"], "description": "Optional; unit not documented by this project."},
        "delaySeconds": {"type": "integer", "description": "Seconds versus schedule, negative means ahead."},
        "nextStopArrival": DATE, "stopId": INTEGER, "stopStatus": STRING,
    }
    arrival_properties = {
        "stopId": INTEGER, "tripId": STRING, "scheduledArrival": DATE, "scheduledDeparture": DATE,
        "arrivalDelay": {"type": "integer", "description": "Seconds; negative means ahead."},
        "departureDelay": INTEGER, "realtime": {"type": "boolean"},
        "wheelchairAccessible": INTEGER, "bikesAllowed": INTEGER,
    }
    definitions = {
        "RawPattern": obj({**raw_pattern_properties, "stops": array(INTEGER), "geometry": {"type": "string", "description": "Encoded polyline, precision 5."}}, ["routeId", "index", "stops"]),
        "Pattern": obj({**raw_pattern_properties, "patternId": STRING, "stopIds": array(INTEGER), "stopCount": INTEGER, "encodedPolyline": STRING}, ["patternId", "routeId", "index", "stopIds", "stopCount"]),
        "RawRoute": obj({**raw_route_properties, "patterns": array(ref("RawPattern"))}, ["id", "shortName", "longName", "type", "patterns"]),
        "Route": obj({**raw_route_properties, "mode": {"enum": ["tram", "bus", "other"]}, "patternCount": INTEGER, "sourceUrl": {"type": "string", "format": "uri"}}, ["id", "shortName", "longName", "type", "mode", "patternCount"]),
        "RouteStop": obj({"routeId": INTEGER, "patternId": STRING, "patternIndex": INTEGER, "stopSequence": {"type": "integer", "minimum": 1}, "stopId": INTEGER}, ["routeId", "patternId", "patternIndex", "stopSequence", "stopId"]),
        "RawStop": obj(raw_stop_properties, ["id", "name", "latitude", "longitude"]),
        "Stop": obj({**raw_stop_properties, "routeIds": array(INTEGER), "sourceUrl": {"type": "string", "format": "uri"}}, ["id", "name", "latitude", "longitude", "routeIds"]),
        "Vehicle": obj(vehicle_properties, ["vehicleId", "routeId", "patternIndex", "latitude", "longitude", "lastUpdated"]),
        "RouteVehicle": obj({**{k: v for k, v in vehicle_properties.items() if k != "stopId"}, "currentStopId": INTEGER, "stopId": INTEGER}, ["vehicleId", "routeId", "latitude", "longitude", "lastUpdated"], "The route-specific endpoint was observed returning currentStopId instead of stopId. Normalize explicitly."),
        "Arrival": obj(arrival_properties, ["stopId", "tripId", "scheduledArrival", "realtime"]),
        "ArrivalSnapshot": obj({**arrival_properties, "routeId": INTEGER, "patternIndex": INTEGER}, ["stopId", "tripId", "routeId", "patternIndex", "scheduledArrival", "realtime"]),
        "ArrivalGroup": obj({"route": obj({"routeId": INTEGER, "index": INTEGER}, ["routeId", "index"]), "times": array(ref("Arrival"))}, ["route", "times"]),
    }
    schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": SITE + "/schema.json",
              "title": "Arad transport public API and normalized export definitions", "$defs": definitions}
    (DOCS / "schema.json").write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n")

    def schema_ref(name):
        return {"$ref": "./schema.json#/$defs/" + name}

    def operation(identifier, summary, response_schema, parameters=None, description=None, static=False):
        op = {"operationId": identifier, "summary": summary, "security": [],
              "responses": {"200": {"description": "JSON response; arrays may be empty.", "content": {"application/json": {"schema": response_schema}}},
                            "default": {"description": "Upstream/network failure. Do not assume a JSON error body; check HTTP status and back off."}}}
        if parameters:
            op["parameters"] = parameters
        if description:
            op["description"] = description
        if static:
            op["servers"] = [{"url": SITE}]
        return {"get": op}

    def id_parameter(name):
        return [{"name": name, "in": "path", "required": True, "schema": INTEGER}]

    paths = {
        "/planner/vehicles": operation("getLiveVehicles", "All publicly available live vehicle positions", array(schema_ref("Vehicle")), description="One request returns all vehicles. No credentials. Poll every 30s in the demo, pause hidden tabs, mark lastUpdated older than 120s stale. These are project conventions, not published operator limits."),
        "/planner/vehicles/route/{routeId}": operation("getRouteVehicles", "Vehicles for an internal route ID", array(schema_ref("RouteVehicle")), id_parameter("routeId")),
        "/planner/routes": operation("getSourceRoutes", "Source routes with embedded patterns", array(schema_ref("RawRoute"))),
        "/planner/routes/{routeId}": operation("getRoutePatterns", "Patterns for a route, returned as an array", array(schema_ref("RawPattern")), id_parameter("routeId")),
        "/planner/stops": operation("getSourceStops", "All source stops", array(schema_ref("RawStop"))),
        "/planner/stops/{stopId}/times": operation("getStopArrivals", "Upcoming arrivals, grouped by route and pattern", array(schema_ref("ArrivalGroup")), id_parameter("stopId"), "Window of upcoming arrivals, not a complete weekly timetable. UTC timestamps. Estimated arrival = scheduledArrival + arrivalDelay seconds only when realtime=true."),
        "/gtfsrt/alerts": operation("getAlerts", "GTFS Realtime alerts as JSON", {"type": "object", "properties": {"header": {"type": "object"}, "entity": array({"type": "object"})}}, [{"name": "mediaType", "in": "query", "schema": {"type": "string", "default": "WebPortal"}}]),
    }
    static_files = {"routes": "Route", "patterns": "Pattern", "routeStops": "RouteStop", "stops": "Stop", "vehiclesSnapshot": "Vehicle", "arrivalsSnapshot": "ArrivalSnapshot"}
    for name, definition in static_files.items():
        paths[f"/data/{name}.json"] = operation("getSnapshot" + name[0].upper() + name[1:], f"Dated static snapshot: {name}", array(schema_ref(definition)), static=True, description="Static file on GitHub Pages. Inspect /data/manifest.json for extraction time. This is not a live endpoint.")
    paths["/data/manifest.json"] = operation("getManifest", "Snapshot provenance, timestamps and file hashes", {"type": "object"}, static=True)
    spec = {"openapi": "3.1.0", "info": {"title": "Arad public transport integration kit", "version": "1.0.0",
             "description": "Observed public Telelink API plus dated GitHub Pages exports. Independent community project. No API key. CORS from GitHub Pages verified 2026-11-07. No upstream reuse license identified; MIT covers project code only."},
            "servers": [{"url": LIVE, "description": "Public upstream live source, not a project relay"}], "security": [], "paths": paths}
    (DOCS / "openapi.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()

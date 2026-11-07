# Source investigation — 2026-11-07

The public page at https://arad-transport.telelink.city/app/lines/route/13 loads a Modeshift web portal inside a WordPress page. Its app root declares `data-settings-url=/wp-content/plugins/planner/data`.

The public `settings.json` under that directory supplies `app.apiUrl=https://www.telelink.city/api/v1` and `app.tenantId=e39aa927-11c1-435f-92b9-57804f7bc1b4`. The frontend bundle `PublicPortal-CAX4lzIb.js`, referenced by the portal version `0.3.0.263`, defines the planner routes, stops, vehicles and stop-times calls. Only public transport GET requests were used. Ticket, account and payment APIs were not accessed.

Verified observations:

- `/planner/routes`: 29 route records with 77 embedded patterns. Types: 0 (8 trams), 3 (21 buses).
- `/planner/stops`: 299 stop records, coordinates and pattern associations.
- `/planner/routes/13`: an array of four patterns. Internal route ID 13 is displayed tram line `3`.
- `/planner/vehicles`: JSON array without authentication. Two initial reads showed 13 vehicles changing coordinates; `lastUpdated` was current UTC.
- `/planner/vehicles/route/23`: verified with a nonempty response; it uses `currentStopId`, while the all-vehicles endpoint uses `stopId`.
- `/planner/stops/97/times`: grouped arrivals, both scheduled and realtime. The exporter subsequently visited all 299 stops and recorded 1,035 arrival rows.
- `/gtfsrt/alerts?mediaType=WebPortal`: a GTFS-RT JSON envelope, with an empty `entity` array at observation time.
- An HTTP request with `Origin: https://baditaflorin.github.io` returned `Access-Control-Allow-Origin: https://baditaflorin.github.io`. Browser verification is performed at publication.

`docs/data/manifest.json` records extraction timestamps, source URLs, response byte counts and SHA-256 for each collection request, including each stop-time request. The full source configuration is intentionally not redistributed: the export retains only relevant public transport endpoint information. No supplied proxy key is needed or published.

Coverage means all records exposed by this portal. Full CTP network coverage, full weekly timetables, source data reuse license, station photos, a downloadable static GTFS archive, WebSocket and SSE were not established. Do not infer these from the API's path names.

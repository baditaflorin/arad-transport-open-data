# Instructions for AI agents using or changing this repository

The main deliverable is a clear, working integration kit for hackathon developers. Prefer Go examples (standard library only); keep JavaScript, Python and curl examples usable too.

Read `README.md`, `docs/llms-full.txt`, `docs/openapi.json` and `docs/schema.json` before integrating data. The live upstream base URL is in `docs/data/manifest.json`. No API key, proxy credential, ticket account, or payment authentication is needed.

Critical contracts:
- `vehiclesSnapshot.*` and `arrivalsSnapshot.*` are dated static snapshots. Fetch `/planner/vehicles` for live positions.
- `routeId` joins `routes[].id`, not `shortName`. Route ID 13 was displayed line 3 in the initial snapshot.
- `patternIndex` can be negative and is scoped to route ID. Use the pair or normalized `patternId`.
- Ordered stop sequences can repeat a stop. Never sort by stop ID or deduplicate the sequence.
- Keep vehicle IDs and trip IDs as strings. Preserve upstream optional fields and nulls.
- GeoJSON coordinate order is longitude, latitude. API fields are explicitly named.
- Show `lastUpdated`; flag positions older than 120s. Fetch once per 30s for all vehicles, pause hidden pages, use bounded timeouts/backoff.
- No explicit upstream data reuse license was identified. MIT covers project code only. Preserve attribution.
- Do not invent station photos, complete weekly timetables, GTFS archives, WebSockets or SSE endpoints.

Before repository work: `git fetch origin --tags`, compare with `origin/main`; use a fresh isolated worktree for changes when applicable.
CI is self-hosted Woodpecker at `https://ci.0exec.com`, root `.woodpecker.yml`. Never add GitHub Actions validation workflows. Pages uses the `main` branch `/docs` folder.

Verify changes with `python3 scripts/validate.py`, `python3 -m unittest discover -s tests -v`, `node --check docs/assets/app.js`, and Go formatting/build/vet in `examples/go`. Do not refetch all arrivals in CI. Run `python3 scripts/export.py --include-arrivals` only for an intentional snapshot refresh; it makes one sequential request per stop, at most 2 requests/s. Export request timeouts are configurable with `ARAD_HTTP_TIMEOUT` or `--timeout`.

Do not commit credentials, access-bearing URLs, proxy keys, local env files, or generated binaries. Do not change shared proxy infrastructure unless it is needed and separately authorized. The direct upstream API currently supports CORS; verify that from a browser before adding a relay.

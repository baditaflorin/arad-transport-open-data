# Arad în mișcare — transport public pentru hackathon

**Vrei autobuzele și tramvaiele pe hartă? Pozițiile live sunt publice, fără cont și fără cheie API.**

- **[Ghidul de integrare](https://baditaflorin.github.io/arad-transport-open-data/api.html)** — începe aici.
- **[Harta, liniile și stațiile](https://baditaflorin.github.io/arad-transport-open-data/)** — demonstrație interactivă.
- **[Descarcă tot pachetul](https://baditaflorin.github.io/arad-transport-open-data/data/arad-transport.zip)** — CSV, JSON, GeoJSON, sursa brută și proveniență.
- **Pentru AI:** [llms.txt](https://baditaflorin.github.io/arad-transport-open-data/llms.txt), [ghid complet](https://baditaflorin.github.io/arad-transport-open-data/llms-full.txt), [OpenAPI](https://baditaflorin.github.io/arad-transport-open-data/openapi.json), [JSON Schema](https://baditaflorin.github.io/arad-transport-open-data/schema.json).

Snapshot inițial, 7 noiembrie 2026: **29 de linii (8 tramvai, 21 autobuz), 77 variante, 299 stații, 805 opriri ordonate și 1.035 sosiri viitoare**. Sunt toate înregistrările returnate de portal la extragere, nu o confirmare independentă că portalul include întreaga rețea CTP. Numerele actuale și ora sunt în [manifest.json](docs/data/manifest.json).

## Începe în 30 de secunde

```sh
# Pozițiile curente: ARRAY JSON, fără autentificare
curl --fail --max-time 20 \
  'https://www.telelink.city/api/v1/e39aa927-11c1-435f-92b9-57804f7bc1b4/transport/planner/vehicles'
```

API-ul acesta este **sursa Telelink folosită de portalul public**, nu un releu găzduit de proiect. Am verificat accesul fără autentificare, CORS din originea GitHub Pages și schimbarea coordonatelor între citiri pe 2026-11-07. Disponibilitatea și compatibilitatea viitoare depind de sursă. GitHub Pages servește separat fișierele statice.

## Go — exemplul principal

```sh
cd examples/go
go run .             # o citire, fără buclă
```

[Client Go complet](examples/go/main.go): folosește numai biblioteca standard, context și timeout de 20s, verifică statusul HTTP, descarcă liniile și stațiile, face join prin ID-uri și semnalează pozițiile mai vechi de două minute. Nu are nevoie de variabile de mediu sau tokenuri.

```go
type Vehicle struct {
    VehicleID   string    `json:"vehicleId"`
    RouteID     int       `json:"routeId"`
    PatternIndex int      `json:"patternIndex"`
    Latitude    float64   `json:"latitude"`
    Longitude   float64   `json:"longitude"`
    LastUpdated time.Time `json:"lastUpdated"`
}
```

Exemple suplimentare: [JavaScript pentru browser/Node](examples/live.mjs), [Python fără dependențe](examples/live.py), plus comanda curl de mai sus.

## API public

```text
LIVE_BASE = https://www.telelink.city/api/v1/e39aa927-11c1-435f-92b9-57804f7bc1b4/transport
DATA_BASE = https://baditaflorin.github.io/arad-transport-open-data/data
```

| Scop | GET, relativ la LIVE_BASE | Răspuns |
|---|---|---|
| Toate vehiculele disponibile | `/planner/vehicles` | `Vehicle[]` |
| Vehicule pentru o linie | `/planner/vehicles/route/{routeId}` | Array; sursa poate folosi `currentStopId` în loc de `stopId` |
| Linii, cu variante și geometrie codificată | `/planner/routes` | Array de linii cu `patterns` |
| Variantele unei linii | `/planner/routes/{routeId}` | Array de variante, nu un obiect linie |
| Stații și coordonate | `/planner/stops` | Array de stații |
| Sosirile viitoare într-o stație | `/planner/stops/{stopId}/times` | `[{route: {routeId, index}, times: [...]}]` |
| Alerte de serviciu | `/gtfsrt/alerts?mediaType=WebPortal` | Obiect GTFS-RT JSON; `entity` poate fi gol |

ID-ul intern al liniei nu este numărul afișat pe vehicul: **`routeId=13` înseamnă linia de tramvai `3`** în snapshot-ul inițial. Nu construi endpoint-uri folosind `shortName`.

## Cum legi datele

```text
vehicle.routeId       → routes[].id           (numărul afișat este shortName)
vehicle.stopId        → stops[].id
vehicle.patternIndex + vehicle.routeId        → patterns[].index + patterns[].routeId
pattern.patternId     → routeStops[].patternId (exemplu: "13:-14")
routeStops[].stopId   → stops[].id
```

- `type=0` este tramvai, `type=3` autobuz; exportul adaugă `mode="tram"|"bus"`.
- `pattern.index` poate fi negativ și este unic **în cadrul liniei**, nu global. Păstrează-l ca atare.
- `direction` poate fi `-1`. Nu-l transforma automat în „tur”/„retur”. Folosește capetele `fromStopId` și `toStopId`.
- `pattern.stopIds` este ordonat. În CSV-ul `routeStops`, `stopSequence` începe de la **1**, pentru fiecare variantă. O stație poate apărea de mai multe ori într-o buclă; nu o deduplica în traseu.
- Stațiile cu același nume pot avea ID-uri și coordonate diferite (sensuri/peron). Fă join prin ID, nu prin nume.
- `vehicleId`, `label`, `tripId` sunt șiruri; nu elimina zerourile inițiale.
- JSON-ul API live are `latitude`, `longitude`; **GeoJSON are `[longitude, latitude]`**, WGS84.
- `lastUpdated` este timpul poziției, în UTC. Tratează o poziție mai veche de **120s** ca învechită. Pragul este o convenție a acestui demo, nu o garanție Telelink.
- `delaySeconds`, `arrivalDelay`, `departureDelay` sunt secunde; valori negative înseamnă devans. `heading` este păstrat ca în sursă. Unitatea câmpului opțional `speed` nu este documentată aici; nu îl afișa automat ca km/h.
- Câmpurile opționale pot lipsi. Array-ul gol este un rezultat valid; nu înseamnă că există vehicule ascunse în alte câmpuri.

## Poziții live: reguli practice

O singură citire aduce toate vehiculele, deci nu face câte un request pentru fiecare marker. Pentru o hartă activă, începe cu **o citire la 30s**, timeout 20s, fără cereri suprapuse, pauză când tabul este ascuns. La eroare, folosește backoff 60s → 120s; afișează ora pozițiilor păstrate. Acestea sunt limite de bună utilizare ale proiectului, nu limite publicate de operator.

Nu am găsit în această investigație un WebSocket/SSE sau un link public verificat la arhiva GTFS statică completă. Datele live disponibile prin HTTP sunt suficiente pentru hartă. Nu este necesară autentificarea de bilete/plăți sau vreun proxy cu cheie privată. Dacă CORS se schimbă, citește API-ul din backendul propriu; nu introduce un proxy public de ocolire cu chei în frontend.

## Fișiere statice

Toate URL-urile de mai jos sunt relative la `DATA_BASE`. Fiecare set are versiuni `.json` și `.csv`.

| Fișier | Conținut |
|---|---|
| `routes` | ID, număr, nume, tip, mod, număr de variante, culori și sursă |
| `patterns` | O variantă per rând, capete, opriri ordonate, polilinie codificată |
| `routeStops` | Opririle expandate: linie, variantă, secvență, stație |
| `stops` | Stații, coordonate, accesibilitate din sursă, liniile asociate |
| `vehiclesSnapshot` | Poziții **la momentul extragerii**, nu live |
| `arrivalsSnapshot` | Fereastra de sosiri viitoare pentru toate cele 299 stații, nu orarul săptămânal complet |
| `routes.geojson` | Câte un LineString pentru fiecare variantă |
| `stops.geojson` | Câte un Point pentru fiecare stație |
| `vehiclesSnapshot.geojson` | Pozițiile din snapshot |
| `raw/*.json` | Răspunsurile sursă pentru linii, stații, vehicule și alerte |
| `manifest.json` | Ora extragerii, URL-uri, numere, hash-uri SHA-256 și momentul fiecărui request |
| `arad-transport.zip` | Pachetul complet |

CSV: UTF-8 cu BOM, delimitator virgulă, ghilimele standard; listele din celule sunt JSON. Preferă `routeStops.csv` când vrei opriri în rânduri separate. JSON: camelCase, valori numerice și null păstrate. Geometria este decodată din polilinia sursei (precizie 5), nu aproximată prin unirea stațiilor.

Nu am identificat fotografii ale stațiilor în răspunsurile analizate. Paginile stațiilor din demo oferă poziția, liniile, sosirile și un link spre împrejurimi pe OpenStreetMap.

## Pentru agenți AI

Începe cu [llms.txt](docs/llms.txt) sau dă agentului acest prompt:

> Integrează transportul Arad folosind https://baditaflorin.github.io/arad-transport-open-data/llms-full.txt și openapi.json din același director. Folosește exemplul Go. Citește pozițiile din API-ul live, liniile și stațiile din snapshot, leagă prin ID și marchează lastUpdated mai vechi de 120 secunde. Nu confunda routeId cu shortName și nu trata vehiclesSnapshot ca live. Nu cere chei API.

Contractul este documentat în [schema.json](docs/schema.json) și [OpenAPI 3.1](docs/openapi.json). Acestea descriu comportamentul observat; proiectul nu deține API-ul Telelink. Codul sursă pentru hartă poate fi citit în [app.js](docs/assets/app.js).

## Reface exportul

Python 3.10+, fără pachete externe:

```sh
python3 scripts/export.py --include-arrivals
python3 scripts/validate.py
python3 -m unittest discover -s tests -v
```

Scriptul citește din configurația publică URL-ul API și tenantul, apoi descarcă datele. Ritmul implicit este cel mult 2 request-uri/s, secvențial; pentru toate sosirile sunt necesare circa 2–4 minute. `--timeout 90` sau `ARAD_HTTP_TIMEOUT=90` modifică timeout-ul la rulare. Maximum trei încercări pentru erori temporare, cu backoff; errno 49 oprește procesul. Datele existente sunt păstrate dacă descărcarea sau validarea sursei eșuează înainte de publicare.

Fără `--include-arrivals`, exportul omite colectarea sosirilor, scrie fișiere de sosiri goale și marchează `arrivalsIncluded=false`. Nu există reîmprospătare automată programată: un nou snapshot se publică printr-un nou commit. Pozițiile live din hartă sunt independente de acest snapshot.

## Dezvoltare și publicare

Site static, fără framework sau build:

```sh
python3 -m http.server 8000 --directory docs --bind 127.0.0.1
# http://127.0.0.1:8000
```

GitHub Pages: branch `main`, folder `/docs`, build de tip branch. Validarea repository-ului este în **Woodpecker, ci.0exec.com**, definită în `.woodpecker.yml`; nu există workflow GitHub Actions de validare. GitHub Pages poate afișa propriul job intern de publicare.

## Proveniență și licență

Sursă: [portalul public Arad / Telelink](https://arad-transport.telelink.city/app/lines/route/13), configurația sa publică și request-urile folosite de aplicația web. Descoperirea endpoint-urilor și probele sunt în [SOURCE.md](SOURCE.md). Niciun token de proxy, secret sau credential nu este necesar sau inclus în acest repository.

**MIT se aplică doar codului proiectului.** Nu a fost identificată o licență explicită de reutilizare a datelor sursă; drepturile și condițiile datelor rămân ale titularilor lor. Acesta este un proiect independent pentru comunitate, fără afiliere oficială cu CTP, Primăria Arad sau Telelink. Leaflet este inclus cu licența sa BSD; harta de bază și atribuirea OpenStreetMap sunt păstrate.

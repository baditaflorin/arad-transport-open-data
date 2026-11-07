#!/usr/bin/env python3
"""Generate AI entrypoints and pre-render the README as a static developer guide."""
import html
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SITE = "https://baditaflorin.github.io/arad-transport-open-data"
REPO = "https://github.com/baditaflorin/arad-transport-open-data/blob/main"
LIVE = "https://www.telelink.city/api/v1/e39aa927-11c1-435f-92b9-57804f7bc1b4/transport"


def public_link(target):
    if target.startswith(("http:", "https:", "#")):
        return target
    if target.startswith("docs/"):
        return SITE + "/" + target[5:]
    return REPO + "/" + target


def inline(text):
    text = html.escape(text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", lambda m: f'<a href="{html.escape(public_link(html.unescape(m[2])), quote=True)}">{m[1]}</a>', text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    return re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)


def render(markdown):
    output, fence, table, listing = [], False, False, False
    for line in markdown.splitlines():
        if line.startswith("```"):
            if fence:
                output.append("</code></pre>")
            else:
                output.append(f'<pre data-language="{html.escape(line[3:])}"><code>')
            fence = not fence
            continue
        if fence:
            output.append(html.escape(line) + "\n")
            continue
        is_table = line.startswith("|")
        if table and not is_table:
            output.append("</tbody></table></div>")
            table = False
        if listing and not line.startswith("- "):
            output.append("</ul>")
            listing = False
        if is_table:
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if all(re.fullmatch(r"[-: ]+", cell) for cell in cells):
                continue
            if not table:
                output.append('<div class="table-scroll"><table><thead><tr>' + ''.join('<th>' + inline(cell) + '</th>' for cell in cells) + '</tr></thead><tbody>')
                table = True
            else:
                output.append('<tr>' + ''.join('<td>' + inline(cell) + '</td>' for cell in cells) + '</tr>')
        elif line.startswith("# "):
            output.append(f'<h1>{inline(line[2:])}</h1>')
        elif line.startswith("## "):
            title = line[3:]
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            output.append(f'<h2 id="{slug}">{inline(title)}</h2>')
        elif line.startswith("- "):
            if not listing:
                output.append("<ul>")
                listing = True
            output.append(f'<li>{inline(line[2:])}</li>')
        elif line.startswith("> "):
            output.append(f'<blockquote>{inline(line[2:])}</blockquote>')
        elif line.strip():
            output.append(f'<p>{inline(line)}</p>')
    if listing:
        output.append("</ul>")
    return '\n'.join(output)


def main():
    readme = (ROOT / "README.md").read_text()
    # AI text uses absolute links; the source README keeps normal repository links.
    ai_readme = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", lambda m: f'[{m[1]}]({public_link(m[2])})', readme)
    (DOCS / "llms-full.txt").write_text(ai_readme)
    (DOCS / "llms.txt").write_text(f"""# Arad public transport integration kit

> Public live buses and trams, routes, stops, CSV/JSON/GeoJSON. Prefer Go examples. No API key required. The upstream is Telelink; GitHub Pages hosts dated static exports only.

## Start here
- [Complete integration guide]({SITE}/llms-full.txt): IDs, joins, freshness, polling, provenance, snapshots, examples.
- [Human-readable guide]({SITE}/api.html)
- [OpenAPI 3.1]({SITE}/openapi.json)
- [JSON Schema]({SITE}/schema.json)
- [Snapshot manifest]({SITE}/data/manifest.json)
- [Go client]({REPO}/examples/go/main.go)
- [Agent instructions]({REPO}/AGENTS.md)

## Live source
- [All vehicle positions]({LIVE}/planner/vehicles): array, unauthenticated. lastUpdated UTC, stale after 120s by demo convention.
- [Source routes]({LIVE}/planner/routes)
- [Source stops]({LIVE}/planner/stops)

## Static files
- [Routes]({SITE}/data/routes.json)
- [Patterns]({SITE}/data/patterns.json)
- [Ordered stops]({SITE}/data/routeStops.json)
- [Stops]({SITE}/data/stops.json)
- [Route geometry]({SITE}/data/routes.geojson)
- [All exports ZIP]({SITE}/data/arad-transport.zip)

Never treat vehiclesSnapshot as live; never join routeId to shortName. Pattern indexes may be negative. GeoJSON is [longitude, latitude]. No full weekly schedule, station photos, verified static GTFS archive or WebSocket endpoint is provided. MIT covers code only; no explicit upstream data license was identified.
""")
    page = f'''<!doctype html><html lang="ro"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>API & ghid pentru programatori · Arad</title><meta name="description" content="Integrează pozițiile live ale autobuzelor și tramvaielor din Arad. Exemple Go, JavaScript, Python, OpenAPI și instrucțiuni pentru AI."><link rel="icon" href="assets/icon.svg"><link rel="stylesheet" href="assets/style.css"><link rel="stylesheet" href="assets/guide.css"></head><body><header class="topbar"><a class="brand" href="./"><span class="brand-icon">a<span>↗</span></span><span>ARAD<span class="brand-sub">KIT PENTRU DEZVOLTATORI</span></span></a><nav><a href="./">Harta</a><a href="llms.txt">Pentru AI ↗</a><a href="https://github.com/baditaflorin/arad-transport-open-data">GitHub ↗</a></nav></header><main class="guide-layout"><aside class="guide-nav"><p class="eyebrow">INTEGRARE RAPIDĂ</p><a href="#ncepe-n-30-de-secunde">Primul request</a><a href="#go-exemplul-principal">Clientul Go</a><a href="#api-public">Endpoint-uri</a><a href="#cum-legi-datele">ID-uri & relații</a><a href="#pozi-ii-live-reguli-practice">Poziții live</a><a href="#fi-iere-statice">Fișiere</a><a href="openapi.json">OpenAPI JSON ↗</a><a href="schema.json">JSON Schema ↗</a><a href="llms-full.txt">Ghid pentru AI ↗</a><a href="data/arad-transport.zip">Tot pachetul ↓</a></aside><article class="guide-content">{render(readme)}</article></main><footer><a href="./">← Înapoi la hartă</a><span>Arad · Date pentru idei noi</span><a href="data/manifest.json">Proveniență ↗</a></footer></body></html>'''
    (DOCS / "api.html").write_text(page)


if __name__ == "__main__":
    main()

/* Public data only. No credentials or proxy services are needed. */
'use strict';
const $ = (selector) => document.querySelector(selector);
const state = { mode: 'all', query: '', routeId: null, patternId: null, stopId: null, vehicles: [], failures: 0 };
let data, map, networkLayer, selectedLayer, stopLayer, vehicleLayer, liveTimer, liveController, arrivalController;
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
const folded = (value) => String(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
const dateTime = (value) => new Intl.DateTimeFormat('ro-RO', { dateStyle: 'short', timeStyle: 'short', timeZone: 'Europe/Bucharest' }).format(new Date(value));
const clockTime = (value) => new Intl.DateTimeFormat('ro-RO', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Bucharest' }).format(new Date(value));

async function getJson(url, signal) {
  const response = await fetch(url, { signal: signal || AbortSignal.timeout(20000), credentials: 'omit' });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function routeName(route) { return route ? `${route.shortName} · ${route.longName}` : 'Linie necunoscută'; }
function stopName(id) { return data.stopById.get(id)?.name || `Stația ${id}`; }
function routeColor(route) { return route?.mode === 'tram' ? '#237266' : '#6176a0'; }
function button(text, className, callback) {
  const node = document.createElement('button');
  node.type = 'button'; node.className = className; node.textContent = text;
  node.addEventListener('click', callback); return node;
}

function renderList() {
  const query = folded(state.query.trim());
  const routes = data.routes.filter((r) => (state.mode === 'all' || r.mode === state.mode) && folded(routeName(r)).includes(query));
  const stops = query ? data.stops.filter((s) => folded(s.name).includes(query) && (state.mode === 'all' || s.routeIds.some((id) => data.routeById.get(id)?.mode === state.mode))) : [];
  $('#list-label').textContent = query ? `${routes.length} LINII · ${stops.length} STAȚII` : `${routes.length} LINII PUBLICATE`;
  const list = $('#route-list'); list.replaceChildren();
  for (const route of routes) {
    const row = button('', `route-row${state.routeId === route.id ? ' selected' : ''}`, () => selectRoute(route.id));
    row.setAttribute('aria-pressed', String(state.routeId === route.id));
    row.innerHTML = `<span class="route-badge ${esc(route.mode)}">${esc(route.shortName)}</span><span class="route-name"><strong>${esc(route.longName)}</strong><small>${route.mode === 'tram' ? 'Tramvai' : 'Autobuz'} · ${route.patternCount} variante</small></span><span class="route-arrow" aria-hidden="true">↗</span>`;
    list.append(row);
  }
  for (const stop of stops.slice(0, 60)) {
    const row = button('', 'route-row station-row', () => selectStop(stop.id));
    row.innerHTML = `<span class="route-badge">○</span><span class="route-name"><strong>${esc(stop.name)}</strong><small>Stația ${esc(stop.id)} · ${stop.routeIds.length} linii</small></span><span class="route-arrow" aria-hidden="true">↗</span>`;
    list.append(row);
  }
  if (stops.length > 60) { const p = document.createElement('p'); p.className = 'empty'; p.textContent = 'Primele 60 de stații. Restrânge căutarea.'; list.append(p); }
  if (!routes.length && !stops.length) { const p = document.createElement('p'); p.className = 'empty'; p.textContent = 'Nu am găsit rezultate. Încearcă alt nume sau număr.'; list.append(p); }
}

function renderNetwork() {
  if (!map) return;
  networkLayer.clearLayers();
  const features = data.geometry.features.filter((f) => state.mode === 'all' || f.properties.mode === state.mode);
  L.geoJSON({ type: 'FeatureCollection', features }, { style: (f) => ({ color: routeColor(f.properties), weight: 2, opacity: state.routeId ? 0.18 : 0.55 }), onEachFeature: (f, layer) => {
    layer.bindTooltip(`Linia ${esc(f.properties.shortName)}`);
    layer.on('click', () => selectRoute(f.properties.routeId, f.properties.patternId));
  } }).addTo(networkLayer);
}

function selectRoute(id, patternId) {
  arrivalController?.abort(); state.stopId = null; state.routeId = id;
  const patterns = data.patterns.filter((p) => p.routeId === id);
  state.patternId = patterns.some((p) => p.patternId === patternId) ? patternId : patterns[0]?.patternId;
  renderList(); renderNetwork(); renderRouteDetail(); renderVehicles();
}

function renderRouteDetail() {
  const route = data.routeById.get(state.routeId);
  const patterns = data.patterns.filter((p) => p.routeId === state.routeId);
  const pattern = patterns.find((p) => p.patternId === state.patternId);
  if (!route || !pattern) return;
  const detail = $('#detail'); detail.hidden = false;
  detail.innerHTML = `<div class="detail-head"><div><p class="eyebrow">${route.mode === 'tram' ? 'TRAMVAI' : 'AUTOBUZ'} · LINIA ${esc(route.shortName)}</p><h2>${esc(route.longName)}</h2><p>${esc(pattern.stopCount)} opriri · Varianta ${esc(pattern.index)} · <a href="${esc(route.sourceUrl)}" target="_blank" rel="noopener">Vezi sursa ↗</a></p></div><label>Varianta de traseu<br><select id="pattern-select" aria-label="Varianta de traseu"></select></label></div><div class="stop-chain"></div>`;
  const select = $('#pattern-select');
  for (const p of patterns) { const option = document.createElement('option'); option.value = p.patternId; option.textContent = `${p.index}: ${stopName(p.fromStopId)} → ${stopName(p.toStopId)} (${p.stopCount} opriri)`; select.append(option); }
  select.value = pattern.patternId;
  select.addEventListener('change', () => { state.patternId = select.value; renderRouteDetail(); $('#pattern-select').focus(); });
  const chain = detail.querySelector('.stop-chain');
  pattern.stopIds.forEach((id, index) => {
    const node = button('', 'stop-chip', () => selectStop(id));
    node.innerHTML = `<span>${index + 1}</span>${esc(stopName(id))}`; chain.append(node);
  });
  drawSelection(pattern);
}

function drawSelection(pattern) {
  if (!map) return;
  selectedLayer.clearLayers();
  const feature = data.geometry.features.find((f) => f.id === pattern.patternId);
  if (feature) L.geoJSON(feature, { style: { color: '#c72d26', weight: 5, opacity: 0.95 } }).addTo(selectedLayer);
  pattern.stopIds.forEach((id) => {
    const s = data.stopById.get(id); if (!s) return;
    L.circleMarker([s.latitude, s.longitude], { radius: 5, fillColor: '#fff', fillOpacity: 1, color: '#c72d26', weight: 2 }).bindTooltip(esc(s.name)).on('click', () => selectStop(id)).addTo(selectedLayer);
  });
  const bounds = selectedLayer.getBounds();
  if (bounds.isValid()) map.fitBounds(bounds, { padding: [40, 60], maxZoom: 15 });
}

function popupForStop(stop) {
  const container = document.createElement('div');
  const title = document.createElement('div'); title.className = 'popup-title'; title.textContent = stop.name;
  const meta = document.createElement('p'); meta.className = 'popup-meta'; meta.textContent = `Stația ${stop.id} · ${stop.routeIds.length} linii`;
  container.append(title, meta, button('Vezi liniile și sosirile →', 'popup-action', () => selectStop(stop.id)));
  return container;
}

async function selectStop(id) {
  arrivalController?.abort(); arrivalController = new AbortController();
  const controller = arrivalController;
  const stop = data.stopById.get(id); if (!stop) return;
  state.stopId = id;
  const detail = $('#detail'); detail.hidden = false;
  detail.innerHTML = `<div class="detail-head"><div><p class="eyebrow">STAȚIA ${esc(stop.id)}</p><h2>${esc(stop.name)}</h2><p>${stop.latitude.toFixed(6)}, ${stop.longitude.toFixed(6)} · <a href="${esc(stop.sourceUrl)}" target="_blank" rel="noopener">Portalul sursă ↗</a> · <a href="https://www.openstreetmap.org/?mlat=${stop.latitude}&mlon=${stop.longitude}#map=18/${stop.latitude}/${stop.longitude}" target="_blank" rel="noopener">Împrejurimi ↗</a></p></div><button class="text-button" id="refresh-arrivals">Reîncarcă sosirile ↻</button></div><div class="stop-chain" id="stop-routes"></div><p style="margin-top:20px" id="arrival-status">Se citesc următoarele sosiri din API…</p><div id="arrival-content"></div>`;
  stop.routeIds.forEach((routeId) => { const route = data.routeById.get(routeId); if (route) $('#stop-routes').append(button(routeName(route), 'stop-chip', () => selectRoute(routeId))); });
  $('#refresh-arrivals').addEventListener('click', () => selectStop(id));
  if (map) { map.setView([stop.latitude, stop.longitude], 16); L.popup().setLatLng([stop.latitude, stop.longitude]).setContent(popupForStop(stop)).openOn(map); }
  const timeout = setTimeout(() => controller.abort(), 20000);
  try {
    const groups = await getJson(data.manifest.endpoints.stopTimes.replace('{stopId}', id), controller.signal);
    if (state.stopId !== id || arrivalController !== controller) return;
    const times = groups.flatMap((g) => g.times.map((t) => ({ ...t, routeId: g.route.routeId })));
    times.sort((a, b) => new Date(a.scheduledArrival).getTime() + (a.arrivalDelay || 0) * 1000 - new Date(b.scheduledArrival).getTime() - (b.arrivalDelay || 0) * 1000);
    $('#arrival-status').textContent = `${times.length} sosiri returnate · Citire ${dateTime(new Date())}. Ore locale; fereastra API, nu orarul săptămânal complet.`;
    if (!times.length) { $('#arrival-content').textContent = 'Nu sunt sosiri în fereastra oferită de sursă.'; return; }
    const table = document.createElement('table'); table.className = 'arrival-table';
    table.innerHTML = '<thead><tr><th>Linie</th><th>Programat</th><th>Estimat</th><th>Sursă</th></tr></thead><tbody></tbody>';
    for (const t of times.slice(0, 50)) {
      const tr = document.createElement('tr');
      const estimated = new Date(new Date(t.scheduledArrival).getTime() + (t.arrivalDelay || 0) * 1000);
      [data.routeById.get(t.routeId)?.shortName || t.routeId, dateTime(t.scheduledArrival), t.realtime ? dateTime(estimated) : '—', t.realtime ? 'Timp real' : 'Orar'].forEach((text) => { const td = document.createElement('td'); td.textContent = text; tr.append(td); });
      table.querySelector('tbody').append(tr);
    }
    $('#arrival-content').append(table);
    if (times.length > 50) { const note = document.createElement('p'); note.textContent = 'Se afișează primele 50 de sosiri; API-ul returnează toate rezultatele.'; $('#arrival-content').append(note); }
  } catch (error) {
    if (state.stopId === id && arrivalController === controller) $('#arrival-status').textContent = `Sosirile nu sunt disponibile acum (${error.name === 'AbortError' ? 'timeout' : error.message}). Poți reîncărca sau consulta portalul sursă.`;
  } finally { clearTimeout(timeout); }
}

function renderVehicles() {
  if (!map) return;
  vehicleLayer.clearLayers();
  for (const vehicle of state.vehicles) {
    const route = data.routeById.get(vehicle.routeId);
    if ((state.routeId && vehicle.routeId !== state.routeId) || (state.mode !== 'all' && route?.mode !== state.mode)) continue;
    if (!Number.isFinite(vehicle.latitude) || !Number.isFinite(vehicle.longitude)) continue;
    const age = Date.now() - new Date(vehicle.lastUpdated).getTime();
    const stale = !Number.isFinite(age) || age > 120000;
    const marker = L.marker([vehicle.latitude, vehicle.longitude], { opacity: stale ? 0.45 : 1, icon: L.divIcon({ className: 'vehicle-icon', html: esc(route?.shortName || '?'), iconSize: [30, 30], iconAnchor: [15, 15] }) });
    marker.bindPopup(`<div class="popup-title">${esc(routeName(route))}</div><p>Vehicul ${esc(vehicle.label)} · ID ${esc(vehicle.vehicleId)}<br>Actualizat: ${esc(dateTime(vehicle.lastUpdated))}${stale ? '<br><strong>Poziție mai veche de 2 minute / timp necunoscut</strong>' : ''}<br>Abatere față de orar: ${esc(vehicle.delaySeconds)} secunde<br>Următoarea stație: ${esc(stopName(vehicle.stopId))}</p>`);
    marker.addTo(vehicleLayer);
  }
}

function stopLive() { clearTimeout(liveTimer); liveController?.abort(); liveController = null; }
async function updateLive() {
  clearTimeout(liveTimer);
  if (!$('#live-toggle').checked || document.hidden || liveController) return;
  const controller = new AbortController(); liveController = controller;
  const timeout = setTimeout(() => controller.abort(), 20000);
  let delay = 30000;
  try {
    const vehicles = await getJson(data.manifest.endpoints.vehicles, controller.signal);
    if (!Array.isArray(vehicles)) throw new Error('Răspuns neașteptat');
    if (!$('#live-toggle').checked || liveController !== controller) return;
    state.vehicles = vehicles; state.failures = 0; renderVehicles();
    const fresh = vehicles.filter((v) => Date.now() - new Date(v.lastUpdated).getTime() <= 120000).length;
    $('#live-status').textContent = `${vehicles.length} vehicule · ${fresh} poziții recente · Citire ${clockTime(new Date())}`;
  } catch (error) {
    if (liveController !== controller || !$('#live-toggle').checked) return;
    state.failures++; delay = Math.min(120000, 30000 * 2 ** state.failures);
    renderVehicles();
    $('#live-status').textContent = `Sursa nu răspunde. ${state.vehicles.length ? 'Poziții păstrate; verifică ora lor. ' : ''}Reîncercare în ${delay / 1000}s.`;
  } finally {
    clearTimeout(timeout);
    if (liveController === controller) { liveController = null; if ($('#live-toggle').checked && !document.hidden) liveTimer = setTimeout(updateLive, delay); }
  }
}

function initializeMap() {
  if (!window.L) { $('#map').innerHTML = '<p class="map-failure">Harta nu s-a încărcat. Lista și exporturile rămân disponibile.</p>'; return; }
  map = L.map('map', { zoomControl: false, scrollWheelZoom: false }).setView([46.182, 21.322], 12);
  L.control.zoom({ position: 'topright' }).addTo(map);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors', maxZoom: 19 }).addTo(map);
  networkLayer = L.featureGroup().addTo(map); selectedLayer = L.featureGroup().addTo(map); stopLayer = L.layerGroup().addTo(map); vehicleLayer = L.layerGroup().addTo(map);
  for (const stop of data.stops) L.circleMarker([stop.latitude, stop.longitude], { radius: 3, weight: 1, color: '#66766a', fillColor: '#fff', fillOpacity: 0.9 }).bindTooltip(esc(stop.name)).bindPopup(() => popupForStop(stop)).addTo(stopLayer);
  renderNetwork();
  const cityStops = data.stops.filter((s) => s.latitude > 46.1 && s.latitude < 46.26 && s.longitude > 21.23 && s.longitude < 21.43);
  if (cityStops.length) map.fitBounds(cityStops.map((s) => [s.latitude, s.longitude]), { padding: [35, 35] });
}

async function main() {
  try {
    const [manifest, routes, patterns, stops, geometry] = await Promise.all(['manifest.json', 'routes.json', 'patterns.json', 'stops.json', 'routes.geojson'].map((name) => getJson(`data/${name}`)));
    routes.sort((a, b) => a.shortName.localeCompare(b.shortName, 'ro', { numeric: true }));
    data = { manifest, routes, patterns, stops, geometry, routeById: new Map(routes.map((r) => [r.id, r])), stopById: new Map(stops.map((s) => [s.id, s])) };
    $('#route-count').textContent = routes.length; $('#stop-count').textContent = stops.length;
    $('#snapshot-date').textContent = `Snapshot · ${dateTime(manifest.fetchedAt)}`;
    const labels = { routes: 'Linii', stops: 'Stații', patterns: 'Variante', routeStops: 'Opriri în ordine', vehiclesSnapshot: 'Vehicule · snapshot', arrivalsSnapshot: 'Sosiri · snapshot' };
    for (const [file, label] of Object.entries(labels)) {
      for (const format of ['csv', 'json']) { const a = document.createElement('a'); a.href = `data/${file}.${format}`; a.download = ''; a.textContent = `${label} / ${format.toUpperCase()}`; $('#file-links').append(a); }
    }
    const geo = document.createElement('a'); geo.href = 'data/stops.geojson'; geo.textContent = 'Stații / GEOJSON'; geo.download = ''; $('#file-links').append(geo);
    initializeMap(); renderList();
    $('#search').addEventListener('input', (event) => { state.query = event.target.value; renderList(); });
    document.querySelectorAll('[data-mode]').forEach((tab) => tab.addEventListener('click', () => {
      state.mode = tab.dataset.mode; state.routeId = null; state.patternId = null; state.stopId = null;
      arrivalController?.abort(); if (map) selectedLayer.clearLayers(); $('#detail').hidden = true;
      document.querySelectorAll('[data-mode]').forEach((other) => { other.classList.toggle('active', other === tab); other.setAttribute('aria-pressed', String(other === tab)); });
      renderList(); renderNetwork(); renderVehicles();
    }));
    $('#reset-view').addEventListener('click', () => {
      state.routeId = null; state.patternId = null; state.stopId = null; state.query = ''; $('#search').value = ''; arrivalController?.abort();
      if (map) { selectedLayer.clearLayers(); map.closePopup(); } $('#detail').hidden = true; renderList(); renderNetwork(); renderVehicles();
      if (map && networkLayer.getBounds().isValid()) map.fitBounds(networkLayer.getBounds(), { padding: [35, 35] });
    });
    $('#live-toggle').addEventListener('change', () => {
      stopLive(); if ($('#live-toggle').checked) { $('#live-status').textContent = 'Se citesc pozițiile din sursă…'; updateLive(); }
      else { state.vehicles = []; renderVehicles(); $('#live-status').textContent = 'Pozițiile live sunt oprite'; }
    });
    document.addEventListener('visibilitychange', () => { stopLive(); if (!document.hidden) updateLive(); });
    const base = new URL('data/', location.href).href;
    $('#code-example').textContent = `const base = '${base}';\n\nconst routes = await fetch(\n  base + 'routes.json'\n).then(response => response.json());\n\nconsole.log(routes[0]);\n// { id, shortName, longName, mode, … }`;
    $('#copy-code').addEventListener('click', async () => { try { await navigator.clipboard.writeText($('#code-example').textContent); $('#copy-code').textContent = 'Copiat ✓'; setTimeout(() => { $('#copy-code').textContent = 'Copiază'; }, 2000); } catch { $('#copy-code').textContent = 'Selectează codul'; } });
  } catch (error) {
    $('#route-list').innerHTML = `<p class="error-message">Datele nu au putut fi încărcate: ${esc(error.message)}. Reîncarcă pagina sau descarcă pachetul ZIP.</p>`;
    $('#snapshot-date').textContent = 'Date indisponibile temporar';
  }
}
main();

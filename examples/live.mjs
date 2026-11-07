// Node 18+ or a browser module. One read; no token or dependency required.
const liveBase = 'https://www.telelink.city/api/v1/e39aa927-11c1-435f-92b9-57804f7bc1b4/transport';
const dataBase = 'https://baditaflorin.github.io/arad-transport-open-data/data';
async function getJSON(url) {
  const response = await fetch(url, { signal: AbortSignal.timeout(20000), credentials: 'omit' });
  if (!response.ok) throw new Error(`HTTP ${response.status}: ${url}`);
  return response.json();
}
const [routes, vehicles] = await Promise.all([
  getJSON(`${dataBase}/routes.json`), getJSON(`${liveBase}/planner/vehicles`),
]);
const byId = new Map(routes.map((route) => [route.id, route]));
console.table(vehicles.map((v) => ({
  line: byId.get(v.routeId)?.shortName ?? `Unknown ID ${v.routeId}`,
  mode: byId.get(v.routeId)?.mode, vehicleId: v.vehicleId,
  latitude: v.latitude, longitude: v.longitude, lastUpdated: v.lastUpdated,
  stale: !v.lastUpdated || Date.now() - Date.parse(v.lastUpdated) > 120000,
})));

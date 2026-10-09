// Read-only probe of the Route Engine's Neon database (via the Route
// Engine's own Prisma client; no Route Engine code is modified).
//
//   node neon_probe.mjs snapshot <out.json>
//   node neon_probe.mjs verify <results.jsonl> <out.json>
//
// snapshot: row counts and latest timestamps.
// verify:   for every route leg the run sent, the MissionRouteState row for
//           its route_engine_mission_id; and RoadConditionEvidence rows
//           created/updated during each scenario's time window.
import { pathToFileURL } from 'node:url';
import path from 'node:path';
import fs from 'node:fs';

const ROUTE_ENGINE_DIR = 'C:/Users/Harsh/Desktop/AASHRAY Route Integration/route_engine';
const [mode, a, b] = process.argv.slice(2);
const files = { in: a && path.resolve(a), out: path.resolve(mode === 'snapshot' ? a : b) };
process.chdir(ROUTE_ENGINE_DIR);
const { default: prisma } = await import(pathToFileURL(path.join(ROUTE_ENGINE_DIR, 'src/config/prisma.js')).href);

async function snapshot() {
  const evidence = await prisma.roadConditionEvidence.aggregate({ _count: true, _max: { createdAt: true, updatedAt: true } });
  const states = await prisma.missionRouteState.aggregate({ _count: true, _max: { createdAt: true, updatedAt: true } });
  return {
    taken_at: new Date().toISOString(),
    road_condition_evidence: { rows: evidence._count, max_created_at: evidence._max.createdAt, max_updated_at: evidence._max.updatedAt },
    mission_route_state: { rows: states._count, max_created_at: states._max.createdAt, max_updated_at: states._max.updatedAt },
  };
}

let result;
if (mode === 'snapshot') {
  result = await snapshot();
} else {
  const recs = fs.readFileSync(files.in, 'utf8').split('\n').filter(Boolean).map(JSON.parse);
  const perScenario = [];
  for (const r of recs) {
    const mission = r.response?.mission?.mission_id;
    const rows = mission
      ? await prisma.missionRouteState.findMany({ where: { missionId: { startsWith: `${mission}-LEG-` } }, orderBy: { missionId: 'asc' } })
      : [];
    const window = { gte: new Date(r.started_at), lte: new Date(r.finished_at) };
    const created = await prisma.roadConditionEvidence.count({ where: { createdAt: window } });
    const updated = await prisma.roadConditionEvidence.count({ where: { updatedAt: window, NOT: { createdAt: window } } });
    perScenario.push({
      scenario_id: r.scenario_id,
      mission_id: mission ?? null,
      mission_route_states: rows.map(s => ({
        missionId: s.missionId, routeStatus: s.routeStatus, primaryRouteId: s.primaryRouteId,
        resourceId: s.resourceId, resourceType: s.resourceType, priority: s.priority,
        source: [s.sourceLatitude, s.sourceLongitude], destination: [s.destinationLatitude, s.destinationLongitude],
        distanceMeters: s.primaryRouteData?.distanceMeters ?? null, createdAt: s.createdAt, updatedAt: s.updatedAt,
      })),
      evidence_rows_created_in_window: created,
      evidence_rows_updated_in_window: updated,
    });
  }
  result = { verified_at: new Date().toISOString(), totals: await snapshot(), scenarios: perScenario };
}

fs.writeFileSync(files.out, JSON.stringify(result, null, 2));
console.log(`wrote ${files.out}`);
await prisma.$disconnect();

import assert from 'node:assert';
import { scoreCandidateRoutes } from '../src/services/routeScoring.service.js';
import { getResourcePolicy } from '../src/services/resourceRiskPolicy.service.js';

console.log('=============================================');
console.log('TEST 5 & 10 — ROUTE RISK SCORING TESTS');
console.log('=============================================\n');

// Controlled candidate routes
// Route A: Shortest travel time (900s), but has ROAD_CLOSED
// Route B: Slightly longer (1200s), no incidents (UNKNOWN)
// Route C: Longest (1500s), affected by moderate TRAFFIC (RISKY)

const routeA = {
  routeId: 'route-A',
  distanceMeters: 8000,
  durationSeconds: 900,
  roadConditionAssessment: {
    status: 'BLOCKED',
    confidence: 'HIGH',
    reasons: [
      {
        type: 'ROAD_CLOSED',
        source: 'OPENWEB_NINJA',
        confidence: 'HIGH',
        ageSeconds: 50
      }
    ]
  },
  matchedIncidents: [
    { incidentId: 'waze-cl-1', conditionType: 'ROAD_CLOSED', confidence: 'HIGH', freshness: 'FRESH' }
  ]
};

const routeB = {
  routeId: 'route-B',
  distanceMeters: 10000,
  durationSeconds: 1200,
  roadConditionAssessment: {
    status: 'UNKNOWN',
    confidence: 'UNKNOWN',
    reasons: []
  },
  matchedIncidents: []
};

const routeC = {
  routeId: 'route-C',
  distanceMeters: 13000,
  durationSeconds: 1500,
  roadConditionAssessment: {
    status: 'RISKY',
    confidence: 'MEDIUM',
    reasons: [
      {
        type: 'TRAFFIC',
        source: 'OPENWEB_NINJA',
        confidence: 'MEDIUM',
        ageSeconds: 120
      }
    ]
  },
  matchedIncidents: [
    { incidentId: 'waze-jam-1', conditionType: 'TRAFFIC', confidence: 'MEDIUM', freshness: 'FRESH', street: 'SV Road', distanceFromRouteMeters: 10 }
  ]
};

const policy = getResourcePolicy({ resourceType: 'RELIEF_TRUCK', priority: 'MEDIUM' });

const scored = scoreCandidateRoutes({
  candidateRoutes: [routeA, routeB, routeC],
  policy
});

console.log('Scored Routes Summary:');
for (const s of scored) {
  console.log(`- ${s.routeId}: status=${s.status}, score=${s.score}, breakdown=`, s.breakdown);
  console.log(`  reasons:`, s.reasons.map(r => r.message));
}

// 1. Route A verification (Shortest time, but BLOCKED)
const scoredA = scored.find(r => r.routeId === 'route-A');
assert.strictEqual(scoredA.status, 'INVALID', 'Route A must be INVALID due to ROAD_CLOSED');
assert.strictEqual(scoredA.score, null, 'INVALID route must have null score');
assert.strictEqual(scoredA.reasons[0].type, 'ROAD_CLOSED');
console.log('\n✓ Route A correctly marked INVALID with null score.');

// 2. Route B verification (No incidents -> VALID with UNKNOWN data / uncertainty penalty)
const scoredB = scored.find(r => r.routeId === 'route-B');
assert.strictEqual(scoredB.status, 'VALID', 'Route B must be VALID');
assert.ok(typeof scoredB.score === 'number' && scoredB.score > 0, 'Route B must have a numeric score');
assert.ok(scoredB.breakdown.uncertaintyScore > 0, 'Route B must carry uncertainty score for lack of evidence');
assert.strictEqual(scoredB.reasons[0].type, 'LIMITED_EVIDENCE');
console.log('✓ Route B verified: VALID with explicit limited evidence / uncertainty indicator (not falsely marked OPEN).');

// 3. Route C verification (Longer travel time and RISKY)
const scoredC = scored.find(r => r.routeId === 'route-C');
assert.strictEqual(scoredC.status, 'VALID', 'Route C must be VALID');
assert.ok(scoredC.score > 0, 'Route C has numeric score');
assert.ok(scoredC.breakdown.roadRiskScore > 0, 'Route C carries roadRiskScore from traffic incident');
console.log('✓ Route C verified: VALID with travel time and road risk penalty.');

console.log('\nALL ROUTE SCORING TESTS PASSED! 🎉');

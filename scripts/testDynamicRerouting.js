import assert from 'node:assert';
import polyline from '@mapbox/polyline';
import { evaluateAndReroute } from '../src/services/rerouting.service.js';
import prisma from '../src/config/prisma.js';

console.log('=============================================');
console.log('TEST 8 — DYNAMIC RE-ROUTING LOGIC TESTS');
console.log('=============================================\n');

async function runReroutingTests() {
  try {
    // Isolated coordinates away from previous test records:
    // e.g. North Mumbai (Borivali/Kandivali): ~19.2200, 72.8500 -> 19.2500, 72.8700
    const source = { latitude: 19.220000, longitude: 72.850000 };
    const destination = { latitude: 19.250000, longitude: 72.870000 };

    // Create polyline for Route A (passes through 19.2350, 72.8600)
    const routeAPoints = [
      [19.220000, 72.850000],
      [19.235000, 72.860000],
      [19.250000, 72.870000]
    ];
    const polylineA = polyline.encode(routeAPoints);

    const initialPrimary = {
      routeId: 'route-initial-A',
      encodedPolyline: polylineA,
      distanceMeters: 4500,
      durationSeconds: 650
    };

    const initialBackup = {
      routeId: 'route-initial-B',
      distanceMeters: 5200,
      durationSeconds: 780
    };

    // Sub-case 1: No blocking evidence -> Reroute NOT required
    console.log('1. Evaluating reroute with clear road conditions...');
    const result1 = await evaluateAndReroute({
      currentRoute: initialPrimary,
      source,
      destination,
      resourceType: 'AMBULANCE',
      priority: 'HIGH',
      currentBackups: [initialBackup]
    });

    assert.strictEqual(result1.rerouted, false, 'Should not reroute when current route is clear');
    assert.strictEqual(result1.newPrimaryRoute.routeId, 'route-initial-A');
    console.log('✓ Sub-case 1 Passed: rerouted=false when route is clear of blocking hazards.');

    // Sub-case 2: Insert fresh blocking evidence directly on Route A
    console.log('\n2. Introducing high-confidence ROAD_CLOSED incident on Route A...');
    const blockingEvidence = await prisma.roadConditionEvidence.create({
      data: {
        source: 'OPENWEB_NINJA',
        externalId: `test-reroute-block-${Date.now()}`,
        conditionType: 'ROAD_CLOSED',
        status: 'BLOCKED',
        latitude: 19.235000,
        longitude: 72.860000,
        severity: 5,
        confidence: 'HIGH',
        reportedAt: new Date(),
        rawMetadata: {
          blockAlertType: 'ROAD_CLOSED',
          freshness: 'FRESH'
        }
      }
    });

    console.log('Stored blocking evidence ID:', blockingEvidence.id);

    // Now evaluate reroute
    const result2 = await evaluateAndReroute({
      currentRoute: initialPrimary,
      source,
      destination,
      resourceType: 'AMBULANCE',
      priority: 'CRITICAL',
      currentBackups: [initialBackup],
      missionId: `mission-test-${Date.now()}`
    });

    assert.strictEqual(result2.rerouted, true, 'Reroute MUST be triggered when route is blocked');
    assert.notStrictEqual(result2.newPrimaryRoute?.routeId, 'route-initial-A', 'New primary route must NOT be blocked Route A');
    assert.ok(result2.reason.includes('ROAD_CLOSED') || result2.reason.includes('Reroute triggered'));
    console.log('✓ Sub-case 2 Passed: Reroute successfully triggered!');
    console.log('  Reroute Reason:', result2.reason);
    console.log('  New Primary Route ID:', result2.newPrimaryRoute?.routeId);

    // Clean up created test evidence
    await prisma.roadConditionEvidence.delete({ where: { id: blockingEvidence.id } });

    console.log('\nALL DYNAMIC REROUTING TESTS PASSED! 🎉');
    await prisma.$disconnect();
    process.exit(0);
  } catch (err) {
    console.error('Rerouting test failed:', err);
    await prisma.$disconnect();
    process.exit(1);
  }
}

runReroutingTests();

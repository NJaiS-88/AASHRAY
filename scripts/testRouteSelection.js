import assert from 'node:assert';
import { selectRoutes } from '../src/services/routeSelection.service.js';

console.log('=============================================');
console.log('TEST 6 — PRIMARY + BACKUP ROUTE SELECTION TESTS');
console.log('=============================================\n');

// Case 1: 3 candidate routes (1 invalid, 2 valid)
console.log('Case 1: 3 candidate routes (1 invalid, 2 valid)...');
const scoredCase1 = [
  { routeId: 'route-A', status: 'INVALID', score: null, reasons: [{ type: 'ROAD_CLOSED', message: 'Road closed' }] },
  { routeId: 'route-B', status: 'VALID', score: 25.5, distanceMeters: 10000, durationSeconds: 1200 },
  { routeId: 'route-C', status: 'VALID', score: 46.0, distanceMeters: 13000, durationSeconds: 1500 }
];

const selection1 = selectRoutes({ scoredRoutes: scoredCase1 });
assert.strictEqual(selection1.status, 'ROUTE_FOUND');
assert.strictEqual(selection1.primaryRoute.routeId, 'route-B', 'Route B must be chosen as PRIMARY (lowest score)');
assert.strictEqual(selection1.backupRoutes.length, 1);
assert.strictEqual(selection1.backupRoutes[0].routeId, 'route-C', 'Route C must be designated as BACKUP');
assert.strictEqual(selection1.rejectedRoutes.length, 1);
assert.strictEqual(selection1.rejectedRoutes[0].routeId, 'route-A', 'Route A must be in rejectedRoutes');
console.log('✓ Case 1 Passed: Route B is PRIMARY, Route C is BACKUP, Route A is REJECTED.');

// Case 2: Only 1 valid candidate route
console.log('\nCase 2: Only 1 valid candidate route...');
const scoredCase2 = [
  { routeId: 'route-only-1', status: 'VALID', score: 15.0, distanceMeters: 5000, durationSeconds: 600 }
];
const selection2 = selectRoutes({ scoredRoutes: scoredCase2 });
assert.strictEqual(selection2.status, 'ROUTE_FOUND');
assert.strictEqual(selection2.primaryRoute.routeId, 'route-only-1');
assert.strictEqual(selection2.backupRoutes.length, 0, 'No backups must be invented when only 1 route exists');
console.log('✓ Case 2 Passed: 1 route correctly designated as PRIMARY without invented backups.');

// Case 3: All routes invalid (e.g. all blocked)
console.log('\nCase 3: All candidate routes invalid...');
const scoredCase3 = [
  { routeId: 'route-X', status: 'INVALID', score: null, reasons: [{ type: 'ROAD_CLOSED', message: 'Overpass collapsed' }] },
  { routeId: 'route-Y', status: 'INVALID', score: null, reasons: [{ type: 'ROAD_BLOCKED', message: 'Debris blocking road' }] }
];
const selection3 = selectRoutes({ scoredRoutes: scoredCase3 });
assert.strictEqual(selection3.status, 'NO_SAFE_ROUTE_FOUND');
assert.strictEqual(selection3.primaryRoute, null);
assert.strictEqual(selection3.backupRoutes.length, 0);
assert.strictEqual(selection3.rejectedRoutes.length, 2);
console.log('✓ Case 3 Passed: Returns NO_SAFE_ROUTE_FOUND when all candidates are blocked.');

console.log('\nALL PRIMARY & BACKUP SELECTION TESTS PASSED! 🎉');

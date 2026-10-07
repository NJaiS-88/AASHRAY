import assert from 'node:assert';
import { evaluateRoadConditions } from '../src/services/roadConditionEngine.service.js';

console.log('=============================================');
console.log('RUNNING ROAD CONDITION ENGINE SERVICE TESTS');
console.log('=============================================\n');

// Rule 1 & 2: No evidence does NOT mean OPEN. No evidence means UNKNOWN.
console.log('Test 1: No evidence gives UNKNOWN status');
const emptyResult = evaluateRoadConditions([]);
assert.strictEqual(emptyResult.status, 'UNKNOWN');
assert.strictEqual(emptyResult.confidence, 'UNKNOWN');
assert.strictEqual(emptyResult.reasons.length, 0);
console.log('✓ Test 1 Passed: empty evidence -> UNKNOWN');

// Rule 3: Fresh high-confidence ROAD_CLOSED produces BLOCKED
console.log('Test 2: Fresh OpenWeb ROAD_CLOSED gives BLOCKED');
const openWebClosed = [{
  source: 'OPENWEB_NINJA',
  conditionType: 'ROAD_CLOSED',
  blockAlertType: 'ROAD_CLOSED',
  confidence: 'HIGH',
  reportedAt: new Date(Date.now() - 41 * 1000) // 41 seconds ago
}];
const closedResult = evaluateRoadConditions(openWebClosed);
assert.strictEqual(closedResult.status, 'BLOCKED');
assert.strictEqual(closedResult.confidence, 'VERY_HIGH');
assert.strictEqual(closedResult.reasons[0].source, 'OPENWEB_NINJA');
assert.strictEqual(closedResult.reasons[0].type, 'ROAD_CLOSED');
assert.ok(closedResult.reasons[0].ageSeconds <= 45);
console.log('✓ Test 2 Passed: OpenWeb ROAD_CLOSED -> BLOCKED, reasons:', closedResult.reasons[0]);

// Rule 4: Responder-confirmed impassable road produces BLOCKED
console.log('Test 3: Responder impassable road gives BLOCKED');
const responderBlocked = [{
  source: 'RESPONDER',
  conditionType: 'ROAD_BLOCKED',
  rawMetadata: { vehiclePassable: false },
  reportedAt: new Date()
}];
const respResult = evaluateRoadConditions(responderBlocked);
assert.strictEqual(respResult.status, 'BLOCKED');
assert.strictEqual(respResult.confidence, 'VERY_HIGH');
console.log('✓ Test 3 Passed: Responder confirmed impassable -> BLOCKED');

// Rule 5: Citizen flooding report produces RISKY/UNKNOWN, not automatically BLOCKED
console.log('Test 4: Citizen flooding report gives RISKY (not BLOCKED)');
const citizenFlood = [{
  source: 'CITIZEN',
  conditionType: 'FLOODED',
  confidence: 'LOW',
  reportedAt: new Date()
}];
const citizenResult = evaluateRoadConditions(citizenFlood);
assert.strictEqual(citizenResult.status, 'RISKY');
assert.notStrictEqual(citizenResult.status, 'BLOCKED');
assert.strictEqual(citizenResult.confidence, 'LOW');
console.log('✓ Test 4 Passed: Citizen flood -> RISKY with LOW confidence');

// Rule 6: Weather influences risk but must NOT mark BLOCKED
console.log('Test 5: Weather report influences risk (RISKY, not BLOCKED)');
const weatherEvent = [{
  source: 'WEATHER',
  conditionType: 'OTHER',
  confidence: 'MEDIUM',
  reportedAt: new Date()
}];
const weatherResult = evaluateRoadConditions(weatherEvent);
assert.strictEqual(weatherResult.status, 'RISKY');
assert.notStrictEqual(weatherResult.status, 'BLOCKED');
console.log('✓ Test 5 Passed: Weather -> RISKY');

// Rule 7 & 8: General gov warning does NOT close all roads, but explicit ROAD_CLOSED produces BLOCKED
console.log('Test 6: Official government road closure gives BLOCKED');
const govClosure = [{
  source: 'GOVERNMENT',
  conditionType: 'ROAD_CLOSED',
  confidence: 'HIGH',
  reportedAt: new Date()
}];
const govResult = evaluateRoadConditions(govClosure);
assert.strictEqual(govResult.status, 'BLOCKED');
assert.strictEqual(govResult.confidence, 'VERY_HIGH');
console.log('✓ Test 6 Passed: Government explicit closure -> BLOCKED');

console.log('\nALL ROAD CONDITION ENGINE TESTS PASSED! 🎉');

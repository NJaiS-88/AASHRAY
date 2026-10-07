import assert from 'node:assert';
import { getResourcePolicy, RESOURCE_POLICIES } from '../src/services/resourceRiskPolicy.service.js';

console.log('=============================================');
console.log('TEST 7 — RESOURCE / VEHICLE POLICY TESTS');
console.log('=============================================\n');

// 1. Ambulance Policy
console.log('1. Checking AMBULANCE policy...');
const ambPolicy = getResourcePolicy({ resourceType: 'AMBULANCE', priority: 'MEDIUM' });
assert.strictEqual(ambPolicy.resourceType, 'AMBULANCE');
assert.strictEqual(ambPolicy.isFallback, false);
assert.strictEqual(ambPolicy.allowedBlocked, false);
assert.strictEqual(ambPolicy.blockingConfidenceThreshold, 'HIGH');
const ambSum = Number((ambPolicy.weights.travelTimeWeight + ambPolicy.weights.roadRiskWeight + ambPolicy.weights.uncertaintyWeight).toFixed(2));
assert.strictEqual(ambSum, 1.0, 'Ambulance weights must sum to 1.0');
console.log('✓ Ambulance policy verified. Weights:', ambPolicy.weights);

// 2. Relief Truck Policy
console.log('\n2. Checking RELIEF_TRUCK policy...');
const truckPolicy = getResourcePolicy({ resourceType: 'RELIEF_TRUCK', priority: 'HIGH' });
assert.strictEqual(truckPolicy.resourceType, 'RELIEF_TRUCK');
assert.strictEqual(truckPolicy.isFallback, false);
assert.strictEqual(truckPolicy.priority, 'HIGH');
const truckSum = Number((truckPolicy.weights.travelTimeWeight + truckPolicy.weights.roadRiskWeight + truckPolicy.weights.uncertaintyWeight).toFixed(2));
assert.strictEqual(truckSum, 1.0, 'Relief truck weights must sum to 1.0');
console.log('✓ Relief Truck policy verified. Weights:', truckPolicy.weights);

// 3. Rescue Vehicle Policy
console.log('\n3. Checking RESCUE_VEHICLE policy...');
const rescuePolicy = getResourcePolicy({ resourceType: 'RESCUE_VEHICLE', priority: 'CRITICAL' });
assert.strictEqual(rescuePolicy.resourceType, 'RESCUE_VEHICLE');
assert.strictEqual(rescuePolicy.isFallback, false);
assert.strictEqual(rescuePolicy.priority, 'CRITICAL');
const rescueSum = Number((rescuePolicy.weights.travelTimeWeight + rescuePolicy.weights.roadRiskWeight + rescuePolicy.weights.uncertaintyWeight).toFixed(2));
assert.strictEqual(rescueSum, 1.0, 'Rescue vehicle weights must sum to 1.0');
console.log('✓ Rescue vehicle policy verified. Weights:', rescuePolicy.weights);

// 4. Unknown Resource Type (Fallback to DEFAULT)
console.log('\n4. Checking unknown resource type fallback...');
const unknownPolicy = getResourcePolicy({ resourceType: 'SUPER_DRONE_UNKNOWN', priority: 'MEDIUM' });
assert.strictEqual(unknownPolicy.resourceType, 'DEFAULT');
assert.strictEqual(unknownPolicy.isFallback, true);
const unknownSum = Number((unknownPolicy.weights.travelTimeWeight + unknownPolicy.weights.roadRiskWeight + unknownPolicy.weights.uncertaintyWeight).toFixed(2));
assert.strictEqual(unknownSum, 1.0, 'Fallback weights must sum to 1.0');
console.log('✓ Unknown resource type correctly fell back to DEFAULT policy:', unknownPolicy.weights);

// 5. Verification of no invented vehicle specs
assert.strictEqual(ambPolicy.maxFloodDepth, undefined, 'Must not invent maxFloodDepth');
assert.strictEqual(truckPolicy.vehicleClearance, undefined, 'Must not invent vehicleClearance');
assert.strictEqual(rescuePolicy.wadingDepth, undefined, 'Must not invent wadingDepth');
console.log('\n✓ Verified: No physical vehicle capabilities or flood depths invented.');

console.log('\nALL RESOURCE POLICY TESTS PASSED! 🎉');

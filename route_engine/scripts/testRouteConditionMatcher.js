import assert from 'node:assert';
import polyline from '@mapbox/polyline';
import {
  decodePolylineToGeoJSON,
  incidentToGeoJSON,
  calculateDistanceToRoute,
  matchIncidentToRoute,
  matchRoutesWithConditions
} from '../src/services/routeConditionMatcher.service.js';

console.log('=============================================');
console.log('RUNNING UNIT TESTS FOR ROUTE CONDITION MATCHER');
console.log('=============================================\n');

// Sample coordinates along a route in Mumbai:
// Point 1: [19.1000, 72.8300]
// Point 2: [19.1100, 72.8400]
// Point 3: [19.1200, 72.8500]
const sampleRouteCoords = [
  [19.1000, 72.8300],
  [19.1100, 72.8400],
  [19.1200, 72.8500]
];
const encodedPolyline = polyline.encode(sampleRouteCoords);
const routeLine = decodePolylineToGeoJSON(encodedPolyline);

// Test 1: Incident directly on route
console.log('Test 1: Incident directly on route');
const incidentOnRoute = {
  id: 'inc-1',
  latitude: 19.1100,
  longitude: 72.8400,
  conditionType: 'TRAFFIC',
  confidence: 'HIGH'
};
const match1 = matchIncidentToRoute(incidentOnRoute, routeLine, 50, 'route-1');
assert.ok(match1 !== null, 'Incident directly on route should match');
assert.strictEqual(match1.distanceFromRouteMeters, 0, 'Distance should be 0 or near 0');
console.log('✓ Test 1 Passed: matched with distance', match1.distanceFromRouteMeters, 'm\n');

// Test 2: Incident far from route (e.g. South Mumbai, >10km away)
console.log('Test 2: Incident far from route');
const incidentFar = {
  id: 'inc-2',
  latitude: 18.9220,
  longitude: 72.8347,
  conditionType: 'ROAD_CLOSED',
  confidence: 'HIGH'
};
const match2 = matchIncidentToRoute(incidentFar, routeLine, 50, 'route-1');
assert.strictEqual(match2, null, 'Incident far away in Mumbai must NOT match');
console.log('✓ Test 2 Passed: correctly ignored far away incident\n');

// Test 3: Incident near but outside tolerance
console.log('Test 3: Incident near but outside tolerance (e.g. 150m away with 50m tolerance)');
// ~0.001 deg lat is ~111m
const incidentNearOutside = {
  id: 'inc-3',
  latitude: 19.1115,
  longitude: 72.8400,
  conditionType: 'ACCIDENT',
  confidence: 'MEDIUM'
};
const geo3 = incidentToGeoJSON(incidentNearOutside);
const dist3 = calculateDistanceToRoute(geo3, routeLine);
console.log(`Calculated distance for near incident: ${dist3.toFixed(1)} meters`);
assert.ok(dist3 > 50, 'Should be farther than 50 meters');
const match3 = matchIncidentToRoute(incidentNearOutside, routeLine, 50, 'route-1');
assert.strictEqual(match3, null, 'Incident outside 50m tolerance should not match');
// But should match if tolerance is increased to 200m
const match3Wide = matchIncidentToRoute(incidentNearOutside, routeLine, 200, 'route-1');
assert.ok(match3Wide !== null, 'Incident should match with 200m tolerance');
console.log('✓ Test 3 Passed: strict tolerance correctly applied\n');

// Test 4: Route with multiple incidents
console.log('Test 4: Route with multiple incidents');
const candidateRouteA = {
  routeId: 'route-A',
  encodedPolyline
};
const incidentsList = [
  { id: 'inc-on-1', latitude: 19.1050, longitude: 72.8350, conditionType: 'TRAFFIC', confidence: 'MEDIUM' },
  { id: 'inc-on-2', latitude: 19.1150, longitude: 72.8450, conditionType: 'ACCIDENT', confidence: 'HIGH' },
  { id: 'inc-far', latitude: 19.2000, longitude: 72.9000, conditionType: 'ROAD_CLOSED', confidence: 'HIGH' }
];
const [matchedRouteA] = matchRoutesWithConditions([candidateRouteA], incidentsList, { toleranceMeters: 50 });
assert.strictEqual(matchedRouteA.affected, true, 'Route A should be affected');
assert.strictEqual(matchedRouteA.matchedIncidents.length, 2, 'Route A should match exactly the 2 nearby incidents');
assert.ok(matchedRouteA.matchedIncidents.some(i => i.incidentId === 'inc-on-1'));
assert.ok(matchedRouteA.matchedIncidents.some(i => i.incidentId === 'inc-on-2'));
console.log(`✓ Test 4 Passed: matched ${matchedRouteA.matchedIncidents.length} incidents on Route A\n`);

// Test 5: Route with a ROAD_CLOSED incident
console.log('Test 5: Route with a ROAD_CLOSED incident');
const closedIncident = {
  id: 'inc-closed',
  latitude: 19.1100,
  longitude: 72.8400,
  blockAlertType: 'ROAD_CLOSED',
  conditionType: 'ROAD_CLOSED',
  confidence: 'HIGH'
};
const [matchedClosedRoute] = matchRoutesWithConditions([candidateRouteA], [closedIncident], { toleranceMeters: 50 });
assert.strictEqual(matchedClosedRoute.affected, true, 'Route should be affected');
assert.strictEqual(matchedClosedRoute.isBlocked, true, 'Route should be marked isBlocked=true');
assert.strictEqual(matchedClosedRoute.blockingCondition, 'ROAD_CLOSED', 'Blocking condition must be ROAD_CLOSED');
console.log('✓ Test 5 Passed: ROAD_CLOSED correctly flagged route as blocked with ROAD_CLOSED\n');

// Extra Test: Route B that does NOT pass through Road 2
console.log('Extra Verification: Route B that does NOT pass through closed road');
const routeCoordsB = [
  [19.0500, 72.8200],
  [19.0600, 72.8250]
];
const candidateRouteB = {
  routeId: 'route-B',
  encodedPolyline: polyline.encode(routeCoordsB)
};
const [matchedRouteB] = matchRoutesWithConditions([candidateRouteB], [closedIncident], { toleranceMeters: 50 });
assert.strictEqual(matchedRouteB.affected, false, 'Route B should not be affected');
assert.strictEqual(matchedRouteB.matchedIncidents.length, 0, 'Route B should have 0 matched incidents');
console.log('✓ Route B unaffected verified.\n');

console.log('ALL 5 UNIT TESTS PASSED SUCCESSFULLY! 🎉');

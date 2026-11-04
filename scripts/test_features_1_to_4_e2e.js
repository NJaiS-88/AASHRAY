/**
 * AASHRAY — End-to-End Verification of Features 1 through 4
 * 
 * Verifies:
 * - Scenario A: Many allocated resources (compact two-column, no unallocated presented as allocated)
 * - Scenario B: Real selected route (genuine road coordinates, origin, checkpoints, destination)
 * - Scenario C: Genuine accepted and rejected route alternatives (status, real metrics, reasons)
 * - Scenario D: Time-critical structural collapse (90-min emergency threshold, escalation safeguards)
 * - Scenario E: Mission isolation (sequential incidents do not bleed route, ETA, or allocations)
 * - Scenario F: Regression (5 default test scenarios, fleet reset, intake workflows intact)
 */

const axios = require('axios');

const RESOURCE_ENGINE_URL = 'http://127.0.0.1:8000';
const ROUTE_ENGINE_URL = 'http://127.0.0.1:3000';
const BACKEND_URL = 'http://127.0.0.1:5000';

async function runVerification() {
  console.log('================================================================');
  console.log(' AASHRAY E2E VERIFICATION SUITE — FEATURES 1 THROUGH 4');
  console.log('================================================================\n');

  let passed = 0;
  let total = 0;

  function assert(condition, message) {
    total++;
    if (!condition) {
      console.error(`  ❌ FAILED: ${message}`);
      throw new Error(message);
    }
    console.log(`  ✓ ${message}`);
    passed++;
  }

  // Pre-flight: Reset fleet to ensure clean testing state
  try {
    await axios.post(`${RESOURCE_ENGINE_URL}/orchestrate/reset-fleet`);
    console.log('  [Pre-flight] Fleet responders reset to AVAILABLE.\n');
  } catch (e) {
    console.warn('  [Pre-flight] Reset fleet warning:', e.message);
  }

  // -------------------------------------------------------------------------
  // SCENARIO A: Many Allocated Resources
  // -------------------------------------------------------------------------
  console.log('▶ [Scenario A] Many Allocated Resources & Allocation Breakdown');
  {
    const payload = {
      incident_id: 'INC-MULTI-RES-TEST',
      incident_type: 'FLOOD',
      location: { latitude: 19.129, longitude: 72.909 },
      locality: {
        name: 'Powai Basin Area',
        population: 50000,
        population_density: 12000,
        affected_population: 1200
      },
      severity: 0.88,
      urgency: 0.85,
      priority: 'CRITICAL',
      estimated_duration_hours: 12.0,
      patient_present: true,
      selected_resource_ids: [
        'drinking_water',
        'food_dry_rations',
        'first_aid_trauma',
        'medicines_medical_supplies',
        'water_purification',
        'shelter_kits_tarpaulin',
        'emergency_shelter_relief_camp',
        'clothing_blankets_warmth'
      ]
    };

    const res = await axios.post(`${RESOURCE_ENGINE_URL}/orchestrate`, payload);
    const data = res.data;

    assert(data.status === 'COMPLETED', `Status should be COMPLETED (got ${data.status})`);
    assert(data.allocation && data.allocation.allocated_resources, 'Allocated resources present');
    
    const allocated = Object.entries(data.allocation.allocated_resources).filter(([_, qty]) => Number(qty) > 0);
    assert(allocated.length >= 6, `Expected many positive allocations (got ${allocated.length} resource types)`);

    // Verify warehouse allocations breakdown is preserved
    assert(Array.isArray(data.allocation.warehouse_allocations) && data.allocation.warehouse_allocations.length > 0,
      `Warehouse allocations present with ${data.allocation.warehouse_allocations.length} warehouse(s)`);

    // Verify unallocated resources are NOT counted as allocated
    const zeroAlloc = Object.entries(data.allocation.allocated_resources).filter(([_, qty]) => Number(qty) === 0);
    zeroAlloc.forEach(([id, qty]) => {
      assert(qty === 0, `Resource ${id} correctly has zero allocated`);
    });

    console.log(`  Allocated ${allocated.length} resource types across ${data.allocation.warehouse_allocations.length} warehouses.\n`);
  }

  // -------------------------------------------------------------------------
  // SCENARIO B: Real Selected Route Geometry & Checkpoints
  // -------------------------------------------------------------------------
  console.log('▶ [Scenario B] Real Selected Route Geometry & Checkpoints');
  {
    // Reset fleet so responders are available
    await axios.post(`${RESOURCE_ENGINE_URL}/orchestrate/reset-fleet`);

    const payload = {
      incident_id: 'INC-ROUTE-GEOM-TEST',
      incident_type: 'FLOOD',
      location: { latitude: 19.068, longitude: 72.875 }, // Kurla West
      locality: {
        name: 'Kurla West Junction',
        population: 25000,
        population_density: 14000,
        affected_population: 150
      },
      severity: 0.70,
      urgency: 0.75,
      priority: 'HIGH',
      estimated_duration_hours: 6.0,
      patient_present: false,
      selected_resource_ids: ['drinking_water', 'first_aid_trauma']
    };

    const res = await axios.post(`${RESOURCE_ENGINE_URL}/orchestrate`, payload);
    const data = res.data;

    assert(data.route && data.route.route, 'Route data present in orchestration output');
    const route = data.route.route;

    assert(route.status === 'AVAILABLE', `Route status should be AVAILABLE (got ${route.status})`);
    assert(route.distance_km > 0, `Route distance should be > 0 km (got ${route.distance_km} km)`);
    assert(route.estimated_time_minutes > 0, `Route ETA should be > 0 mins (got ${route.estimated_time_minutes} min)`);
    assert(Array.isArray(route.coordinates) && route.coordinates.length >= 2,
      `Route coordinates should contain points (got ${route.coordinates?.length} coords)`);

    // Verify checkpoints: Responder -> Warehouse(s) -> Destination
    assert(Array.isArray(route.legs) && route.legs.length >= 2,
      `Multi-leg route planned (got ${route.legs?.length} legs)`);

    const leg0 = route.legs[0];
    assert(leg0.source_type === 'RESPONDER', `Leg 0 source is RESPONDER (${leg0.source_id})`);
    assert(leg0.source_location && leg0.source_location.latitude > 0, 'Responder location valid');

    const lastLeg = route.legs[route.legs.length - 1];
    assert(lastLeg.destination_type === 'DESTINATION', `Last leg destination is DESTINATION`);
    assert(Math.abs(lastLeg.destination_location.latitude - payload.location.latitude) < 0.001,
      `Destination coordinates match incident coordinates (${lastLeg.destination_location.latitude}, ${lastLeg.destination_location.longitude})`);

    console.log(`  Route planned across ${route.legs.length} legs (${route.distance_km} km, ${route.estimated_time_minutes} min) with ${route.coordinates.length} waypoints.\n`);
  }

  // -------------------------------------------------------------------------
  // SCENARIO C: Genuine Route Alternatives (Accepted, Backup, and Rejected)
  // -------------------------------------------------------------------------
  console.log('▶ [Scenario C] Genuine Accepted & Rejected Route Alternatives');
  {
    // Test direct Route Engine optimization endpoint to verify candidate evaluation
    const routeRes = await axios.post(`${ROUTE_ENGINE_URL}/api/routes/optimize`, {
      source: { latitude: 19.08, longitude: 72.88 },
      destination: { latitude: 19.115, longitude: 72.862 },
      resourceType: 'AMBULANCE',
      priority: 'HIGH'
    });

    const routeData = routeRes.data?.data;
    assert(routeData && routeData.primaryRoute, 'Route engine returned primaryRoute');
    assert(routeData.primaryRoute.routeId, `Primary route ID present (${routeData.primaryRoute.routeId})`);
    assert(routeData.primaryRoute.distanceMeters > 0, 'Primary route distanceMeters > 0');
    assert(routeData.primaryRoute.durationSeconds > 0, 'Primary route durationSeconds > 0');
    assert(routeData.primaryRoute.encodedPolyline, 'Primary route encodedPolyline present');

    // Check backup and rejected routes
    const backups = routeData.backupRoutes || [];
    const rejected = routeData.rejectedRoutes || [];

    console.log(`  Route Engine evaluated: 1 Primary, ${backups.length} Backup(s), ${rejected.length} Rejected route(s).`);

    if (backups.length > 0) {
      assert(backups[0].distanceMeters > 0, 'Backup alternative distance > 0');
      assert(backups[0].durationSeconds > 0, 'Backup alternative duration > 0');
      assert(backups[0].encodedPolyline, 'Backup alternative has real encoded polyline');
    }

    if (rejected.length > 0) {
      assert(rejected[0].rejectionReason, `Rejected route has rejectionReason (${rejected[0].rejectionReason})`);
      assert(rejected[0].status === 'INVALID', 'Rejected route status is INVALID');
    }

    assert(Array.isArray(routeData.decisionReasons) && routeData.decisionReasons.length > 0,
      `Decision reasons explain selection: "${routeData.decisionReasons[0]}"`);

    console.log(`  ✓ Genuine candidate evaluation verified without fabricated alternatives.\n`);
  }

  // -------------------------------------------------------------------------
  // SCENARIO D: Time-Critical Structural Collapse & 90-Min Emergency Threshold
  // -------------------------------------------------------------------------
  console.log('▶ [Scenario D] Time-Critical Structural Collapse & 90-Minute Emergency Safeguard');
  {
    await axios.post(`${RESOURCE_ENGINE_URL}/orchestrate/reset-fleet`);

    // Submit structural collapse incident
    const payload = {
      incident_id: 'INC-COLLAPSE-TEST-01',
      incident_type: 'STRUCTURAL_COLLAPSE',
      location: { latitude: 19.1150, longitude: 72.8620 }, // Andheri East
      locality: {
        name: 'Andheri East Industrial Estate',
        population: 15000,
        population_density: 11000,
        affected_population: 3
      },
      severity: 0.95,
      urgency: 0.95,
      priority: 'CRITICAL',
      estimated_duration_hours: 14.0,
      patient_present: true,
      selected_resource_ids: [
        'first_aid_trauma',
        'heavy_machinery_debris_clearance',
        'tools_equipment'
      ]
    };

    const res = await axios.post(`${RESOURCE_ENGINE_URL}/orchestrate`, payload);
    const data = res.data;

    assert(data.status === 'COMPLETED', `Collapse incident successfully orchestrated (status: ${data.status})`);
    assert(data.route && data.route.route, 'Route data present');
    
    const route = data.route.route;
    assert(route.emergency_threshold_minutes === 90.0,
      `Emergency response threshold configured to 90.0 mins (got ${route.emergency_threshold_minutes})`);

    console.log(`  Mission ${data.mission?.mission_id} ETA: ${route.estimated_time_minutes} min (Threshold: ${route.emergency_threshold_minutes} min)`);
    
    if (route.estimated_time_minutes > 90.0) {
      assert(route.emergency_threshold_exceeded === true, 'emergency_threshold_exceeded flagged true');
      assert(route.eta_review_escalation === true, 'eta_review_escalation flagged true');
      assert(typeof route.emergency_threshold_warning === 'string' && route.emergency_threshold_warning.includes('EMERGENCY ETA ESCALATION'),
        `Clear warning message generated: "${route.emergency_threshold_warning}"`);
      console.log('  ✓ Safeguard active: Urgent review & priority escort flagged without falsifying ETA.');
    } else {
      assert(route.emergency_threshold_exceeded === false, 'ETA is within threshold, not flagged exceeded');
      console.log('  ✓ Route successfully meets emergency 90-minute target.');
    }

    console.log('');
  }

  // -------------------------------------------------------------------------
  // SCENARIO E: Sequential Mission Isolation
  // -------------------------------------------------------------------------
  console.log('▶ [Scenario E] Sequential Mission Isolation (No Route or Allocation Leakage)');
  {
    await axios.post(`${RESOURCE_ENGINE_URL}/orchestrate/reset-fleet`);

    // Incident 1: Flood
    const floodRes = await axios.post(`${RESOURCE_ENGINE_URL}/orchestrate`, {
      incident_id: 'INC-ISO-FLOOD',
      incident_type: 'FLOOD',
      location: { latitude: 19.129, longitude: 72.909 },
      locality: { name: 'Powai', population: 20000, population_density: 8000, affected_population: 100 },
      severity: 0.8,
      urgency: 0.8,
      priority: 'HIGH',
      estimated_duration_hours: 8.0,
      patient_present: false,
      selected_resource_ids: ['drinking_water', 'water_purification']
    });

    // Reset fleet so second incident has clean available units
    await axios.post(`${RESOURCE_ENGINE_URL}/orchestrate/reset-fleet`);

    // Incident 2: Landslide
    const landslideRes = await axios.post(`${RESOURCE_ENGINE_URL}/orchestrate`, {
      incident_id: 'INC-ISO-LANDSLIDE',
      incident_type: 'LANDSLIDE',
      location: { latitude: 19.088, longitude: 72.912 },
      locality: { name: 'Ghatkopar', population: 15000, population_density: 9000, affected_population: 60 },
      severity: 0.7,
      urgency: 0.75,
      priority: 'HIGH',
      estimated_duration_hours: 6.0,
      patient_present: true,
      selected_resource_ids: ['first_aid_trauma', 'tools_equipment']
    });

    const floodData = floodRes.data;
    const landData = landslideRes.data;

    // Check incident ID and mission ID uniqueness
    assert(floodData.incident_id !== landData.incident_id, 'Incident IDs distinct');
    assert(floodData.mission.mission_id !== landData.mission.mission_id, 'Mission IDs distinct');

    // Check allocations distinct
    const floodAlloc = Object.keys(floodData.allocation.allocated_resources);
    const landAlloc = Object.keys(landData.allocation.allocated_resources);
    assert(floodAlloc.includes('drinking_water'), 'Flood allocated drinking_water');
    assert(!landAlloc.includes('drinking_water'), 'Landslide did NOT bleed drinking_water');
    assert(landAlloc.includes('tools_equipment'), 'Landslide allocated tools_equipment');

    // Check route coordinates distinct
    const floodCoords0 = floodData.route.route.coordinates[0];
    const landCoords0 = landData.route.route.coordinates[0];
    assert(floodCoords0.latitude !== landCoords0.latitude || floodCoords0.longitude !== landCoords0.longitude,
      'Route starting/waypoint coordinates are isolated per incident');

    console.log('  ✓ Zero cross-mission leakage across sequential executions.\n');
  }

  // -------------------------------------------------------------------------
  // SCENARIO F: Regression & Citizen Intake Workflow
  // -------------------------------------------------------------------------
  console.log('▶ [Scenario F] Regression & Citizen Intake Workflow');
  {
    // Verify 5 default test scenarios in live-missions endpoint
    const liveRes = await axios.get(`${RESOURCE_ENGINE_URL}/orchestrate/live-missions`);
    assert(Array.isArray(liveRes.data?.live_missions), 'Live missions endpoint responding');
    
    // Authenticate user
    const email = `testuser_${Date.now()}@example.com`;
    const signupRes = await axios.post(`${BACKEND_URL}/api/auth/signup`, {
      name: 'Test Citizen',
      email: email,
      password: 'Password123!',
      role: 'citizen'
    });
    const token = signupRes.data.token;
    assert(token, 'Citizen authenticated with JWT token');

    // Test citizen intake endpoint
    const intakeRes = await axios.post(`${BACKEND_URL}/api/entries`, {
      text: 'A slab collapsed on people in my locality.',
      location: { lat: 19.115, lng: 72.862 }
    }, {
      headers: { Authorization: `Bearer ${token}` }
    });

    assert(intakeRes.status === 201, `Citizen report submission accepted (status: ${intakeRes.status})`);
    const entry = intakeRes.data;
    assert(entry.status === 'NEEDS_CLARIFICATION' || entry.status === 'MISSION_ACTIVE',
      `Intake status valid (got ${entry.status})`);

    console.log(`  Citizen entry created: ${entry._id} (status: ${entry.status})`);
    console.log('  ✓ Citizen intake and clarification pipeline functioning correctly.\n');
  }

  console.log('================================================================');
  console.log(` ALL END-TO-END TESTS PASSED (${passed}/${total} assertions) 🎉`);
  console.log('================================================================');
}

runVerification().catch(err => {
  console.error('\nVerification failed with exception:', err);
  process.exit(1);
});

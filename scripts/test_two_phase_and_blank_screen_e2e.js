const axios = require('axios');

async function runVerification() {
  console.log('========================================================================');
  console.log('AASHRAY E2E VERIFICATION: Two-Phase Missions & Blank Screen Fix');
  console.log('========================================================================\n');

  let passed = 0;
  let failed = 0;

  function assert(condition, message) {
    if (condition) {
      console.log(`  [PASS] ${message}`);
      passed++;
    } else {
      console.error(`  [FAIL] ${message}`);
      failed++;
    }
  }

  const BASE_URL = 'http://127.0.0.1:8000';

  // 1. Reset test data first
  try {
    const resetRes = await axios.post(`${BASE_URL}/orchestrate/reset-fleet`);
    assert(resetRes.status === 200, 'Fleet reset endpoint succeeded');
  } catch (e) {
    assert(false, `Fleet reset failed: ${e.message}`);
  }

  // 2. Test Time-Critical Incident triggers Two-Phase Emergency Mission
  console.log('\n--- 1. Testing Two-Phase Emergency Mission Trigger ---');
  try {
    const collapsePayload = {
      incident_id: `INC-COLLAPSE-${Date.now()}`,
      incident_type: 'STRUCTURAL_COLLAPSE',
      location: { latitude: 19.0760, longitude: 72.8777 },
      locality: {
        name: 'Kurla Building Slab Collapse Sector',
        population: 15000,
        population_density: 8500,
        affected_population: 20
      },
      severity: 0.9,
      urgency: 0.95,
      priority: 'CRITICAL',
      estimated_duration_hours: 12.0,
      patient_present: true,
      hazard_details: ['Slab fell on 3 people, trapped under rubble', 'Severe crushing trauma']
    };

    const res = await axios.post(`${BASE_URL}/orchestrate`, collapsePayload);
    assert(res.status === 200, 'Two-phase orchestration returned HTTP 200');
    assert(res.data.phase === 'TWO_PHASE_COORDINATED', 'Parent orchestration phase is TWO_PHASE_COORDINATED');
    assert(Array.isArray(res.data.sub_missions) && res.data.sub_missions.length === 2, 'Result contains exactly 2 linked sub-missions');

    const phaseA = res.data.sub_missions[0];
    const phaseB = res.data.sub_missions[1];

    assert(phaseA.phase === 'IMMEDIATE_RESPONSE', 'Sub-mission A is IMMEDIATE_RESPONSE');
    assert(phaseA.mission?.mission_id?.endsWith('-A'), 'Sub-mission A ID ends with -A');
    assert(phaseA.agent_assignment !== null, 'Sub-mission A has assigned responder');

    assert(phaseB.phase === 'FOLLOW_UP_LOGISTICS', 'Sub-mission B is FOLLOW_UP_LOGISTICS');
    assert(phaseB.mission?.mission_id?.endsWith('-B'), 'Sub-mission B ID ends with -B');
    assert(phaseB.agent_assignment !== null, 'Sub-mission B has assigned responder');

    // Responders are distinct
    const respA = phaseA.agent_assignment?.responder_id;
    const respB = phaseB.agent_assignment?.responder_id;
    assert(respA !== respB, `Phase A (${respA}) and Phase B (${respB}) assigned distinct responders`);

    // Resource partition check
    const immediateKeys = ['search_and_rescue', 'first_aid_trauma', 'emergency_medical_care', 'tools_equipment', 'heavy_machinery_debris_clearance'];
    const allocAKeys = Object.keys(phaseA.allocation?.allocated_resources || {});
    const allocBKeys = Object.keys(phaseB.allocation?.allocated_resources || {});

    const allAImmediate = allocAKeys.every(k => immediateKeys.includes(k));
    assert(allAImmediate, 'Sub-mission A contains strictly immediate life-saving rescue/medical resources');

    const noBImmediate = allocBKeys.every(k => !immediateKeys.includes(k));
    assert(noBImmediate, 'Sub-mission B contains strictly follow-up logistics/supplies');

    // Shared inventory reconciliation check (zero double allocation)
    const overlap = allocAKeys.filter(k => allocBKeys.includes(k));
    assert(overlap.length === 0, 'Zero resource key overlap between Phase A and Phase B (sequential inventory deduction)');

    // Combined allocation equals sum
    let allocationSumConsistent = true;
    for (const [k, v] of Object.entries(phaseA.allocation?.allocated_resources || {})) {
      if (res.data.allocation?.allocated_resources[k] !== v) allocationSumConsistent = false;
    }
    for (const [k, v] of Object.entries(phaseB.allocation?.allocated_resources || {})) {
      if (res.data.allocation?.allocated_resources[k] !== v) allocationSumConsistent = false;
    }
    assert(allocationSumConsistent, 'Combined parent allocation mathematically equals sum of Phase A and Phase B');

    // Independent routes check
    assert(phaseA.route?.routing_inputs?.responder_id === respA, 'Route A inputs match Responder A');
    assert(phaseB.route?.routing_inputs?.responder_id === respB, 'Route B inputs match Responder B');
    console.log(`    Phase A ETA: ${phaseA.route?.route?.estimated_time_minutes} mins`);
    console.log(`    Phase B ETA: ${phaseB.route?.route?.estimated_time_minutes} mins`);

  } catch (e) {
    assert(false, `Two-phase orchestration test threw error: ${e.response?.data?.detail || e.message}`);
  }

  // 3. Test Non-Time-Critical Incident preserves single phase
  console.log('\n--- 2. Testing Non-Time-Critical Single Phase Preservation ---');
  try {
    const floodPayload = {
      incident_id: `INC-FLOOD-${Date.now()}`,
      incident_type: 'FLOOD',
      location: { latitude: 19.0176, longitude: 72.8561 },
      locality: {
        name: 'Dadar Lowlands',
        population: 25000,
        population_density: 10000,
        affected_population: 50
      },
      severity: 0.7,
      urgency: 0.6,
      priority: 'HIGH',
      estimated_duration_hours: 8.0,
      patient_present: false,
      hazard_details: ['Waterlogging 2 feet']
    };

    const res = await axios.post(`${BASE_URL}/orchestrate`, floodPayload);
    assert(res.status === 200, 'Flood orchestration returned HTTP 200');
    assert(res.data.phase === 'SINGLE_PHASE', 'Flood orchestration phase is SINGLE_PHASE');
    assert(!res.data.sub_missions || res.data.sub_missions.length === 0, 'No sub-missions generated for standard flood incident');
    assert(res.data.mission?.mission_id?.startsWith('MIS-'), 'Single mission ID created');
    assert(!res.data.mission?.mission_id?.endsWith('-A'), 'Mission ID is not suffixed with -A');
  } catch (e) {
    assert(false, `Single phase test threw error: ${e.response?.data?.detail || e.message}`);
  }

  // 4. Test Live Missions Persistence with Two-Phase Details
  console.log('\n--- 3. Testing Live Missions Persistence ---');
  try {
    const liveRes = await axios.get(`${BASE_URL}/orchestrate/live-missions`);
    assert(liveRes.status === 200, 'GET /orchestrate/live-missions returned HTTP 200');
    const missions = liveRes.data.live_missions || [];
    assert(missions.length > 0, `Live missions list populated (${missions.length} records)`);
    const collapseMission = missions.find(m => m.incident_type === 'STRUCTURAL_COLLAPSE');
    assert(collapseMission !== undefined, 'Structural collapse live mission found in persistence store');
    assert(collapseMission?.full_orchestration?.sub_missions?.length === 2, 'Persisted mission contains 2 sub-missions for frontend consumption');
  } catch (e) {
    assert(false, `Live missions test threw error: ${e.message}`);
  }

  // 5. Test Frontend Static Asset Validation
  console.log('\n--- 4. Frontend Blank Screen Regression Check ---');
  try {
    const fs = require('fs');
    const code = fs.readFileSync('resource_engine/frontend/src/pages/ResourceRouteOrchestration.jsx', 'utf-8');
    assert(!code.includes('incident={current}'), 'No undefined "current" reference in JSX render scope');
    assert(code.includes('incident={selectedRow}'), 'Incident prop correctly passes "selectedRow" to RouteMapComponent');
    assert(code.includes('prev[currentIncidentId]'), 'State updater correctly uses "currentIncidentId"');
    assert(code.includes('executionResult.sub_missions?.length === 2'), 'Two-Phase Coordination display integrated into JSX');

    const mapCode = fs.readFileSync('resource_engine/frontend/src/components/RouteMapComponent.jsx', 'utf-8');
    assert(mapCode.includes('MapErrorBoundary'), 'MapErrorBoundary wrapper defends map crashes');
    assert(mapCode.includes('filter(pt => !isNaN(pt[0])'), 'Defensive coordinate filtering active');
  } catch (e) {
    assert(false, `Frontend check failed: ${e.message}`);
  }

  console.log('\n========================================================================');
  console.log(`SUMMARY: ${passed} PASSED, ${failed} FAILED`);
  console.log('========================================================================');

  if (failed > 0) {
    process.exit(1);
  }
}

runVerification();

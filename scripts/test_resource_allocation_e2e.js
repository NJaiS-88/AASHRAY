const BASE_URL = 'http://localhost:5000/api';
const RE_URL = 'http://localhost:8000';

async function runTests() {
    console.log('================================================================');
    console.log(' AASHRAY — CITIZEN MISSION ALLOCATION E2E VERIFICATION SUITE');
    console.log('================================================================');
    let passed = 0;
    let failed = 0;

    function assert(condition, message) {
        if (condition) {
            console.log(`[PASS] ${message}`);
            passed++;
        } else {
            console.error(`[FAIL] ${message}`);
            failed++;
        }
    }

    try {
        // Register test citizen user
        const citizenEmail = `citizen_alloc_${Date.now()}@example.com`;
        const authRes = await fetch(`${BASE_URL}/auth/signup`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: 'Citizen Alloc Tester', email: citizenEmail, password: 'password123' })
        });
        const { token } = await authRes.json();
        assert(token, 'Citizen test user registered and authenticated');

        // =================================================================
        // TEST A: Successful Allocation (Flood in Powai)
        // =================================================================
        console.log('\n--- TEST A: Successful Allocation Flow (Powai Flood) ---');
        const reportA = await fetch(`${BASE_URL}/entries`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
            body: JSON.stringify({
                text: 'Severe flood in Powai near lake, water entering houses, 15 people stranded',
                location: { lat: 19.1197, lng: 72.9056 }
            })
        });
        const entryA = await reportA.json();
        assert(reportA.status === 201, `Incident A submitted successfully (HTTP ${reportA.status})`);
        assert(entryA.status === 'MISSION_ACTIVE', `Entry A transitioned to MISSION_ACTIVE (got ${entryA.status})`);
        assert(entryA.missionUpdate != null, 'Entry A received missionUpdate');
        assert(entryA.missionUpdate.mission_id != null, `Mission ID assigned: ${entryA.missionUpdate?.mission_id}`);
        assert(entryA.missionUpdate.status === 'RESOURCES_DISPATCHED' || entryA.missionUpdate.status === 'QUEUED_FOR_DISPATCH', `Mission status valid: ${entryA.missionUpdate?.status}`);
        assert(entryA.missionUpdate.confirmed_resources?.length > 0, `Confirmed resources count: ${entryA.missionUpdate?.confirmed_resources?.length}`);
        
        // Validate specific resource properties
        const resourcesA = entryA.missionUpdate?.confirmed_resources || [];
        const drinkingWater = resourcesA.find(r => r.resource_id === 'drinking_water');
        assert(drinkingWater && drinkingWater.quantity > 0, `Drinking water allocated: ${drinkingWater?.quantity} ${drinkingWater?.unit}`);
        const boats = resourcesA.find(r => r.resource_id === 'boat_water_rescue');
        assert(boats && boats.quantity > 0, `Water rescue boats allocated: ${boats?.quantity} ${boats?.unit}`);
        assert(entryA.missionUpdate.eta_display && !entryA.missionUpdate.eta_display.includes('Calculating route ETA'), `Route ETA calculated: ${entryA.missionUpdate?.eta_display}`);

        // =================================================================
        // TEST B: Partial Fulfillment Scenario
        // =================================================================
        console.log('\n--- TEST B: Partial Fulfillment (Extreme Demand) ---');
        const rePartialRes = await fetch(`${RE_URL}/orchestrate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                incident_id: `INC-PARTIAL-${Date.now()}`,
                incident_type: 'flood',
                location: { latitude: 19.1197, longitude: 72.9056 },
                locality: {
                    name: 'Mega Disaster Zone',
                    population: 500000,
                    population_density: 5000.0,
                    affected_population: 50000,
                },
                severity: 0.95,
                urgency: 0.95,
                priority: 'CRITICAL',
                estimated_duration_hours: 48.0,
                patient_present: true
            })
        });
        const partialData = await rePartialRes.json();
        assert(
            partialData.fulfilment_status === 'PARTIALLY_FULFILLED' || partialData.allocation?.allocation_status === 'PARTIALLY_FULFILLED',
            `Partial fulfillment status reported correctly: ${partialData.fulfilment_status || partialData.allocation?.allocation_status}`
        );
        const reqWater = partialData.allocation?.required_resources?.drinking_water || 0;
        const allocWater = partialData.allocation?.allocated_resources?.drinking_water || 0;
        assert(allocWater < reqWater, `Allocated water (${allocWater}) < Required water (${reqWater}) reflects stock limits`);

        // =================================================================
        // TEST C: Zero Allocation / Pending Differentiation
        // =================================================================
        console.log('\n--- TEST C: Pending / Clarification State Differentiation ---');
        const vagueReport = await fetch(`${BASE_URL}/entries`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
            body: JSON.stringify({
                text: 'Something happened outside my window',
                location: { lat: 19.1197, lng: 72.9056 }
            })
        });
        const vagueEntry = await vagueReport.json();
        assert(vagueEntry.status === 'NEEDS_CLARIFICATION', `Vague entry flagged for clarification (got ${vagueEntry.status})`);
        assert(!vagueEntry.missionUpdate || vagueEntry.missionUpdate?.confirmed_resources?.length === 0, 'No false allocation created for unclarified report');

        // =================================================================
        // TEST D: Multiple Distinct Missions (Clarification Flow + No Bleed)
        // =================================================================
        console.log('\n--- TEST D: Multiple Distinct Missions (Clarification to Allocation) ---');
        // Initial submission triggers clarification for population
        const reportLandslide = await fetch(`${BASE_URL}/entries`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
            body: JSON.stringify({
                text: 'Landslide in Ghatkopar hilly area, mud collapsed onto 4 shanties, heavy debris clearance needed',
                location: { lat: 19.0860, lng: 72.9080 }
            })
        });
        const initialLS = await reportLandslide.json();
        assert(initialLS.status === 'NEEDS_CLARIFICATION', 'Landslide initial intake paused for population clarification');

        // User answers clarification with affected population
        const clarifyRes = await fetch(`${BASE_URL}/entries/${initialLS._id}/clarify`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
            body: JSON.stringify({
                clarification: '12 people are trapped in the debris',
                affected_population: 12,
                incident_type: 'landslide'
            })
        });
        const entryLandslide = await clarifyRes.json();
        assert(entryLandslide.status === 'MISSION_ACTIVE', `Clarified landslide transitioned to MISSION_ACTIVE (got ${entryLandslide.status})`);
        assert(entryLandslide.missionUpdate != null, 'Landslide received missionUpdate after clarification');
        assert(entryLandslide.missionUpdate?.mission_id !== entryA.missionUpdate?.mission_id, 'Distinct mission ID assigned to Landslide');
        
        const landslideResources = entryLandslide.missionUpdate?.confirmed_resources || [];
        const hasDebrisEquipment = landslideResources.some(r => r.resource_id === 'heavy_machinery_debris_clearance' || r.resource_id === 'tools_equipment');
        const hasBoatsInLandslide = landslideResources.some(r => r.resource_id === 'boat_water_rescue');
        assert(hasDebrisEquipment, 'Landslide received heavy machinery / debris tools');
        assert(!hasBoatsInLandslide, 'Landslide correctly did NOT receive boats (no resource bleeding from Flood A)');

        // =================================================================
        // TEST E: Regression & Data Integrity (5 Default Incidents)
        // =================================================================
        console.log('\n--- TEST E: Regression & 5 Default Incidents Integrity ---');
        const liveMissionsRes = await fetch(`${RE_URL}/orchestrate/live-missions`);
        const liveMissionsData = await liveMissionsRes.json();
        assert(Array.isArray(liveMissionsData.live_missions), 'Live missions endpoint healthy and returning array');

        // Check entries fetch for user (verifies GET /api/entries serialization)
        const userEntriesRes = await fetch(`${BASE_URL}/entries`, {
            headers: { Authorization: `Bearer ${token}` }
        });
        const userEntries = await userEntriesRes.json();
        assert(userEntries.length >= 3, `User entries fetch returns all submitted threads (count: ${userEntries.length})`);
        const fetchedA = userEntries.find(e => e._id === entryA._id);
        assert(fetchedA?.missionUpdate?.confirmed_resources?.length > 0, 'Fetched entry retains populated confirmed_resources');

    } catch (err) {
        console.error('Test execution exception:', err.message);
        failed++;
    }

    console.log(`\n================================================================`);
    console.log(` SUMMARY: ${passed} passed, ${failed} failed`);
    console.log(`================================================================`);
    process.exit(failed > 0 ? 1 : 0);
}

runTests();

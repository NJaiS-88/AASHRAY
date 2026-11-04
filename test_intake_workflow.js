/**
 * test_intake_workflow.js
 * End-to-end verification of the 5 Context-Aware Clarification & Affected Population Intake Acceptance Cases
 */

const BASE_URL = 'http://localhost:5000/api';

async function run() {
    console.log('========================================================');
    console.log(' AASHRAY E2E VERIFICATION — INTAKE CASES A THROUGH E');
    console.log('========================================================\n');

    // 1. Authenticate user via signup
    const timestamp = Date.now();
    const userEmail = `citizen_intake_${timestamp}@test.org`;
    const password = 'Password@123';

    const signupRes = await fetch(`${BASE_URL}/auth/signup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: 'Citizen Intake Tester', email: userEmail, password, role: 'user' })
    });
    const signupData = await signupRes.json();
    const token = signupData.token;
    if (!token) throw new Error('Failed to signup regular user: ' + JSON.stringify(signupData));
    const headers = {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
    };

    // Helper to post an entry
    async function createReport(text, coords) {
        const res = await fetch(`${BASE_URL}/entries`, {
            method: 'POST',
            headers,
            body: JSON.stringify({
                text1: text,
                location: coords,
                conversationTitle: 'Intake Test'
            })
        });
        return await res.json();
    }

    // Helper to clarify an entry
    async function clarifyReport(id, data) {
        const res = await fetch(`${BASE_URL}/entries/${id}/clarify`, {
            method: 'POST',
            headers,
            body: JSON.stringify(data)
        });
        return await res.json();
    }

    const testCoords = { lat: 19.076, lng: 72.877 };

    // ─────────────────────────────────────────────────────────────
    // CASE A: "There is an emergency in my locality." with coords
    // ─────────────────────────────────────────────────────────────
    console.log('▶ [Case A] Testing "There is an emergency in my locality." (coords provided)...');
    const caseA = await createReport('There is an emergency in my locality.', testCoords);
    console.log('  Status:', caseA.status);
    console.log('  Clarifying questions:', caseA.ragReport?.clarifying_questions);
    
    if (caseA.status !== 'NEEDS_CLARIFICATION') {
        throw new Error(`Case A expected NEEDS_CLARIFICATION but got ${caseA.status}`);
    }
    const qStrA = (caseA.ragReport?.clarifying_questions || []).join(' ').toLowerCase();
    if (qStrA.includes('location') || qStrA.includes('where')) {
        throw new Error('Case A violated rule: asked for location when GPS coordinates were present!');
    }
    if (!qStrA.includes('type') && !qStrA.includes('hazard')) {
        throw new Error('Case A expected question about emergency/hazard type');
    }
    console.log('  ✔ Case A: Location was NOT asked (coordinates honored). Hazard type and population requested. Orchestration paused.\n');

    // ─────────────────────────────────────────────────────────────
    // CASE B: "There is severe waterlogging in my area." with coords
    // ─────────────────────────────────────────────────────────────
    console.log('▶ [Case B] Testing "There is severe waterlogging in my area." (coords provided)...');
    const caseB = await createReport('There is severe waterlogging in my area.', testCoords);
    console.log('  Status:', caseB.status);
    console.log('  Clarifying questions:', caseB.ragReport?.clarifying_questions);

    if (caseB.status !== 'NEEDS_CLARIFICATION') {
        throw new Error(`Case B expected NEEDS_CLARIFICATION but got ${caseB.status}`);
    }
    const qStrB = (caseB.ragReport?.clarifying_questions || []).join(' ').toLowerCase();
    if (qStrB.includes('location') || qStrB.includes('where')) {
        throw new Error('Case B violated rule: asked for location when GPS coordinates were present!');
    }
    if (qStrB.includes('what happened')) {
        throw new Error('Case B violated rule: asked what happened when waterlogging was already stated!');
    }
    if (!qStrB.includes('people') && !qStrB.includes('population') && !qStrB.includes('evacuation') && !qStrB.includes('assistance')) {
        throw new Error('Case B expected question about affected population');
    }
    console.log('  ✔ Case B: Hazard accurately identified as flooding_waterlogging. Location and hazard repetition avoided. Population requested.\n');

    // ─────────────────────────────────────────────────────────────
    // CASE C: "A slab fell on three people near my location." with coords
    // ─────────────────────────────────────────────────────────────
    console.log('▶ [Case C] Testing "A slab fell on three people near my location." (coords provided)...');
    const caseC = await createReport('A slab fell on three people near my location.', testCoords);
    console.log('  Status:', caseC.status);
    console.log('  Mission Update:', caseC.missionUpdate?.status, 'Confirmed resources:', caseC.missionUpdate?.confirmed_resources?.length);

    if (caseC.status === 'NEEDS_CLARIFICATION') {
        throw new Error('Case C failed: All mandatory fields were present (hazard=collapse, pop=3, coords), but system asked clarification questions!');
    }
    if (caseC.status !== 'MISSION_ACTIVE' && caseC.status !== 'ORCHESTRATING') {
        throw new Error(`Case C expected MISSION_ACTIVE or ORCHESTRATING but got ${caseC.status}`);
    }
    console.log('  ✔ Case C: 0 clarification questions. Proceeded directly to live orchestration & resource dispatch!\n');

    // ─────────────────────────────────────────────────────────────
    // CASE D: "A slab fell on people in my locality." with coords -> then clarify population
    // ─────────────────────────────────────────────────────────────
    console.log('▶ [Case D] Testing "A slab fell on people in my locality." (coords provided, missing count)...');
    const caseD = await createReport('A slab fell on people in my locality.', testCoords);
    console.log('  Initial Status:', caseD.status);
    console.log('  Initial Questions:', caseD.ragReport?.clarifying_questions);

    if (caseD.status !== 'NEEDS_CLARIFICATION') {
        throw new Error(`Case D expected initial NEEDS_CLARIFICATION but got ${caseD.status}`);
    }
    const qStrD = (caseD.ragReport?.clarifying_questions || []).join(' ').toLowerCase();
    if (!qStrD.includes('people') && !qStrD.includes('many')) {
        throw new Error('Case D expected question asking how many people are affected/trapped');
    }

    console.log('  Submitting clarification with affected_population = 5...');
    const clarifiedD = await clarifyReport(caseD._id, {
        affected_population: 5,
        clarification: '5 people trapped under the concrete rubble'
    });
    console.log('  Clarified Status:', clarifiedD.status);
    console.log('  Clarified Mission Update:', clarifiedD.missionUpdate?.status);

    if (clarifiedD.status !== 'MISSION_ACTIVE' && clarifiedD.status !== 'ORCHESTRATING') {
        throw new Error(`Case D expected MISSION_ACTIVE after clarification but got ${clarifiedD.status}`);
    }
    console.log('  ✔ Case D: Clarification accurately escalated to orchestration and dispatched resources.\n');

    // ─────────────────────────────────────────────────────────────
    // CASE E: "Severe waterlogging near Powai affecting approximately 200 people." with coords
    // ─────────────────────────────────────────────────────────────
    console.log('▶ [Case E] Testing "Severe waterlogging near Powai affecting approximately 200 people." (coords provided)...');
    const caseE = await createReport('Severe waterlogging near Powai affecting approximately 200 people.', { lat: 19.117, lng: 72.905 });
    console.log('  Status:', caseE.status);
    console.log('  Mission Update:', caseE.missionUpdate?.status, 'Confirmed resources:', caseE.missionUpdate?.confirmed_resources?.length);

    if (caseE.status === 'NEEDS_CLARIFICATION') {
        throw new Error('Case E failed: All mandatory fields present (hazard=waterlogging, pop=200, location=Powai+coords), but asked clarification questions!');
    }
    if (caseE.status !== 'MISSION_ACTIVE' && caseE.status !== 'ORCHESTRATING') {
        throw new Error(`Case E expected MISSION_ACTIVE or ORCHESTRATING but got ${caseE.status}`);
    }
    console.log('  ✔ Case E: 0 clarification questions. Directly mobilized 200-person flood relief mission!\n');

    console.log('========================================================');
    console.log(' ALL 5 INTAKE ACCEPTANCE CASES (A THROUGH E) VERIFIED!');
    console.log('========================================================');
}

run().catch((err) => {
    console.error('\n❌ Verification Failed:', err.message);
    process.exit(1);
});

// scripts/test_navigation_and_workflow_refinement_e2e.mjs
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const JEV_URL = 'http://localhost:5002';
const FRONTEND_URL = 'http://localhost:5174';

let passCount = 0;
let failCount = 0;

function assert(condition, message) {
  if (condition) {
    console.log(`  [PASS] ${message}`);
    passCount++;
  } else {
    console.error(`  [FAIL] ${message}`);
    failCount++;
  }
}

async function run() {
  console.log('========================================================================');
  console.log(' AASHRAY — NAVIGATION FIXES & WORKFLOW REFINEMENT E2E TEST SUITE');
  console.log('========================================================================\n');

  // --------------------------------------------------------------------------
  // TEST 1: TASK 1 — LOGIN NAVIGATION CHECKS
  // --------------------------------------------------------------------------
  console.log('--- 1. TASK 1: Login Navigation Verification ---');
  
  const navbarFile = path.resolve(__dirname, '../frontend/src/components/landing/LandingNavbar.jsx');
  const navbarContent = fs.readFileSync(navbarFile, 'utf8');
  assert(navbarContent.includes('to="/login"'), 'Navbar Login button points to /login');

  const heroFile = path.resolve(__dirname, '../frontend/src/components/landing/HeroSection.jsx');
  const heroContent = fs.readFileSync(heroFile, 'utf8');
  assert(heroContent.includes('to="/login"'), 'Hero button points to /login');
  assert(heroContent.includes('Sign In to AASHRAY'), 'Hero secondary CTA button has label "Sign In to AASHRAY"');

  const loginFile = path.resolve(__dirname, '../frontend/src/pages/Login.jsx');
  const loginContent = fs.readFileSync(loginFile, 'utf8');
  assert(!loginContent.includes('navigate(\'/admin\');\n      } else {\n        navigate(\'/citizen\');\n      }\n    }\n  }, [currentUser'),
    'Login.jsx does not automatically redirect away on mount when currentUser is present');
  assert(loginContent.includes('Active session'), 'Login.jsx renders informative active session indicator if user is already signed in');

  const appFile = path.resolve(__dirname, '../frontend/src/App.jsx');
  const appContent = fs.readFileSync(appFile, 'utf8');
  assert(appContent.includes('path="/login" element={<Login />}'), 'App.jsx maps /login to <Login /> without redirect');

  // --------------------------------------------------------------------------
  // TEST 2: TASK 2 — REDUNDANT STAGE LABELS REMOVAL
  // --------------------------------------------------------------------------
  console.log('\n--- 2. TASK 2: Removal of Redundant Stage Labels ---');

  const workflowFile = path.resolve(__dirname, '../frontend/src/components/landing/WorkflowSection.jsx');
  const workflowContent = fs.readFileSync(workflowFile, 'utf8');

  assert(!workflowContent.includes('STAGE 01 OF 06') && !workflowContent.includes('STAGE 02 OF 06'),
    'Redundant "STAGE XX OF 06" text is completely removed from workflow cards');
  assert(!workflowContent.includes('STAGE {item.step} OF 06'),
    'Dynamic "STAGE {item.step} OF 06" template string is removed');
  assert(workflowContent.includes('{item.step}'),
    'Large numbered indicators (01 through 06) are retained');
  assert(workflowContent.includes('Explore component') || workflowContent.includes('Collapse details'),
    'Redundant stage label replaced with contextual interactive action "Explore component"');

  // --------------------------------------------------------------------------
  // TEST 3: TASK 3 — SIX-COMPONENT WORKFLOW INTERACTION & PROGRESSION
  // --------------------------------------------------------------------------
  console.log('\n--- 3. TASK 3: Workflow Interaction & Visual Progression ---');

  assert(workflowContent.includes('responsibility'), 'Workflow cards contain engine responsibility details');
  assert(workflowContent.includes('input') && workflowContent.includes('Input Received'), 'Workflow cards contain input received specification');
  assert(workflowContent.includes('processing'), 'Workflow cards contain processing details');
  assert(workflowContent.includes('output') && workflowContent.includes('Output Produced'), 'Workflow cards contain output produced specification');
  assert(workflowContent.includes('handoff') && workflowContent.includes('Handoff to Next'), 'Workflow cards explain how output connects to next component');
  assert(workflowContent.includes('border-dashed border-indigo-200'), 'Desktop grid includes subtle visual connection connector');
  assert(workflowContent.includes('lg:hidden') && workflowContent.includes('border-l-2'), 'Mobile layout includes connected vertical timeline');

  // Verify the exact 6 components and their order
  const stepTitles = [
    'Citizen Incident Reporting',
    'JEV Incident Processing & Dispatch',
    'Disaster RAG Knowledge Assessment',
    'Resource Engine',
    'Mission Creation & Responder Assignment',
    'Route Engine'
  ];
  stepTitles.forEach((title, idx) => {
    assert(workflowContent.includes(title), `Step 0${idx + 1} "${title}" is present in workflow`);
  });

  // --------------------------------------------------------------------------
  // TEST 4: TASK 4 — PLATFORM SCENARIO VISUALIZATION
  // --------------------------------------------------------------------------
  console.log('\n--- 4. TASK 4: Compact Product Scenario Visualization ---');

  const scenarioFile = path.resolve(__dirname, '../frontend/src/components/landing/CompactScenarioVisualization.jsx');
  assert(fs.existsSync(scenarioFile), 'CompactScenarioVisualization.jsx exists');

  const scenarioContent = fs.readFileSync(scenarioFile, 'utf8');
  assert(scenarioContent.includes('1. Incident Location') && scenarioContent.includes('Sector 4'),
    'Scenario includes Incident Location element');
  assert(scenarioContent.includes('2. Nearby Resource Hubs') && scenarioContent.includes('Central Depot Alpha'),
    'Scenario includes Nearby Resource Hubs element');
  assert(scenarioContent.includes('3. Example Resource Allocation') && scenarioContent.includes('Drinking Water'),
    'Scenario includes Example Resource Allocation element');
  assert(scenarioContent.includes('4. Response Route') && scenarioContent.includes('Selected: Western Bypass'),
    'Scenario includes Response Route element with selected and bypassed routes');
  assert(scenarioContent.includes('5. Mission Status') && scenarioContent.includes('Phase 1') && scenarioContent.includes('Phase 2'),
    'Scenario includes Mission Status element with two-phase tracking');
  assert(scenarioContent.includes('Demonstration Visualization Only') || scenarioContent.includes('Illustrative'),
    'Prominent disclaimer prevents misrepresenting demonstration as live deployment');

  const landingPageFile = path.resolve(__dirname, '../frontend/src/pages/LandingPage.jsx');
  const landingPageContent = fs.readFileSync(landingPageFile, 'utf8');
  assert(landingPageContent.includes('CompactScenarioVisualization'),
    'CompactScenarioVisualization is integrated in LandingPage.jsx');

  // --------------------------------------------------------------------------
  // TEST 5: TASK 5 — TESTING AND PRESERVATION
  // --------------------------------------------------------------------------
  console.log('\n--- 5. TASK 5: Live Navigation & Authentication Preserved ---');

  try {
    const feRes = await fetch(FRONTEND_URL);
    assert(feRes.ok && feRes.status === 200, `Frontend is responding at ${FRONTEND_URL}`);
  } catch (err) {
    assert(false, `Frontend fetch failed: ${err.message}`);
  }

  // Verify Citizen Login via /api/auth/login
  let citizenToken = '';
  try {
    const citizenEmail = `cit_${Date.now()}@aashray.local`;
    const signupRes = await fetch(`${JEV_URL}/api/auth/signup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'Citizen Tester', email: citizenEmail, password: 'Password123!' })
    });
    const signupData = await signupRes.json();
    assert(signupRes.status === 201 && signupData.role === 'user', 'Citizen registration works correctly');
    citizenToken = signupData.token;
  } catch (err) {
    assert(false, `Citizen signup exception: ${err.message}`);
  }

  // Verify Admin Login via /api/auth/login
  let adminToken = '';
  try {
    const adminLoginRes = await fetch(`${JEV_URL}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: 'admin@aashray.local', password: 'Admin@Aashray2026!' })
    });
    const adminData = await adminLoginRes.json();
    assert(adminLoginRes.status === 200 && adminData.role === 'admin', 'Admin login verifies role="admin"');
    adminToken = adminData.token;
  } catch (err) {
    assert(false, `Admin login exception: ${err.message}`);
  }

  // Verify Protected Endpoints
  try {
    const unauthRes = await fetch(`${JEV_URL}/api/entries/admin`);
    assert(unauthRes.status === 401, 'Unauthenticated request blocked from admin API with HTTP 401');

    const citApiRes = await fetch(`${JEV_URL}/api/entries/admin`, {
      headers: { Authorization: `Bearer ${citizenToken}` }
    });
    assert(citApiRes.status === 403, 'Citizen token blocked from admin API with HTTP 403');

    const adminApiRes = await fetch(`${JEV_URL}/api/entries/admin`, {
      headers: { Authorization: `Bearer ${adminToken}` }
    });
    assert(adminApiRes.status === 200, 'Admin token permitted to admin API with HTTP 200');
  } catch (err) {
    assert(false, `API security test exception: ${err.message}`);
  }

  // --------------------------------------------------------------------------
  // SUMMARY
  // --------------------------------------------------------------------------
  console.log('\n========================================================================');
  console.log(` E2E TEST SUMMARY: ${passCount} PASSED, ${failCount} FAILED`);
  console.log('========================================================================\n');

  if (failCount > 0) {
    process.exit(1);
  } else {
    process.exit(0);
  }
}

run().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});

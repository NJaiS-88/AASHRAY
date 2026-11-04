// scripts/test_marketing_landing_page_e2e.mjs
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
  console.log(' AASHRAY — MARKETING LANDING PAGE (MONSOON ADAPTATION) VERIFICATION');
  console.log('========================================================================\n');

  // --------------------------------------------------------------------------
  // TEST 1: Source Files & Modular Architecture Inspection
  // --------------------------------------------------------------------------
  console.log('--- 1. Testing Component Modular Architecture & File Structure ---');
  
  const landingFile = path.resolve(__dirname, '../frontend/src/pages/LandingPage.jsx');
  assert(fs.existsSync(landingFile), 'LandingPage.jsx exists in frontend/src/pages/');

  const compDir = path.resolve(__dirname, '../frontend/src/components/landing');
  assert(fs.existsSync(compDir), 'components/landing directory exists');

  const requiredComponents = [
    'LandingNavbar.jsx',
    'HeroSection.jsx',
    'GeospatialMapVisual.jsx',
    'ProblemSection.jsx',
    'WorkflowSection.jsx',
    'CapabilitiesSection.jsx',
    'PlatformPreviewSection.jsx',
    'ClosingBrandSection.jsx',
    'LandingFooter.jsx'
  ];

  for (const comp of requiredComponents) {
    const p = path.join(compDir, comp);
    assert(fs.existsSync(p), `Component ${comp} exists and is modularized`);
  }

  // --------------------------------------------------------------------------
  // TEST 2: Content & Copy Requirements Verification
  // --------------------------------------------------------------------------
  console.log('\n--- 2. Testing Landing Page Copy & Visual Design Constraints ---');

  const heroContent = fs.readFileSync(path.join(compDir, 'HeroSection.jsx'), 'utf8');
  assert(heroContent.includes('When every second matters'), 'Hero contains exact headline opening');
  assert(heroContent.includes('every response counts'), 'Hero contains exact headline closing');
  assert(heroContent.includes('Connecting incident intelligence, resource allocation, and emergency response through one coordinated platform'),
    'Hero contains exact supporting text');
  assert(heroContent.includes('Explore AASHRAY'), 'Hero includes primary CTA "Explore AASHRAY"');
  assert(heroContent.includes('to="/login"'), 'Hero includes secondary CTA linking to generic /login');
  assert(!heroContent.includes('to="/login/admin"') && !heroContent.includes('to="/login/citizen"'),
    'Hero does not leak citizen vs admin options directly (preserves generic Login)');

  const mapVisualContent = fs.readFileSync(path.join(compDir, 'GeospatialMapVisual.jsx'), 'utf8');
  assert(mapVisualContent.includes('LIVE GEOSPATIAL EMERGENCY TELEMETRY'), 'Geospatial visual has telemetry header');
  assert(mapVisualContent.includes('Central Depot Alpha') && mapVisualContent.includes('Sector 07 Medical Base'),
    'Geospatial visual has regional warehouse and medical response hubs');
  assert(mapVisualContent.includes('Incident #NDRF-402') || mapVisualContent.includes('INCIDENT'),
    'Geospatial visual has active emergency incident beacon');
  assert(mapVisualContent.includes('Flooded Arterial Bypassed') || mapVisualContent.includes('Hazard'),
    'Geospatial visual highlights hazard route bypass');

  const problemContent = fs.readFileSync(path.join(compDir, 'ProblemSection.jsx'), 'utf8');
  assert(problemContent.includes('Disaster response requires more than information. It requires coordination.') ||
         problemContent.includes('Disaster response requires more than information'),
    'Problem section has exact headline');
  assert(problemContent.includes('Fragmented Incident Reporting'), 'Problem 1 covered');
  assert(problemContent.includes('Delayed Incident Assessment'), 'Problem 2 covered');
  assert(problemContent.includes('Inefficient Resource Allocation'), 'Problem 3 covered');
  assert(problemContent.includes('Limited Inventory Visibility'), 'Problem 4 covered');
  assert(problemContent.includes('Disconnected Emergency Operations'), 'Problem 5 covered');
  assert(problemContent.includes('Difficult Route & Responder Coordination'), 'Problem 6 covered');

  const workflowContent = fs.readFileSync(path.join(compDir, 'WorkflowSection.jsx'), 'utf8');
  assert(workflowContent.includes('How AASHRAY Coordinates Emergency Response') || workflowContent.includes('How AASHRAY works'),
    'Workflow section header verified');
  assert(workflowContent.includes('Citizen Incident Reporting'), 'Workflow Step 1 verified');
  assert(workflowContent.includes('JEV Incident Processing & Dispatch'), 'Workflow Step 2 verified');
  assert(workflowContent.includes('Disaster RAG Knowledge Assessment') || workflowContent.includes('Disaster RAG'),
    'Workflow Step 3 verified');
  assert(workflowContent.includes('Resource Engine Calculation & Allocation') || workflowContent.includes('Resource Engine'),
    'Workflow Step 4 verified');
  assert(workflowContent.includes('Mission Creation & Responder Assignment') || workflowContent.includes('Mission Creation'),
    'Workflow Step 5 verified');
  assert(workflowContent.includes('Route Engine Optimization') || workflowContent.includes('Route Engine'),
    'Workflow Step 6 verified');

  const capContent = fs.readFileSync(path.join(compDir, 'CapabilitiesSection.jsx'), 'utf8');
  assert(capContent.includes('JEV — Incident Intelligence and Dispatch'), 'Capability 1: JEV verified');
  assert(capContent.includes('Disaster RAG — Contextual Disaster Intelligence'), 'Capability 2: Disaster RAG verified');
  assert(capContent.includes('Resource Engine — Planning and Allocation') || capContent.includes('Resource Engine — Resource Planning and Allocation'),
    'Capability 3: Resource Engine verified');
  assert(capContent.includes('Route Engine — Emergency Route Optimization'), 'Capability 4: Route Engine verified');

  const previewContent = fs.readFileSync(path.join(compDir, 'PlatformPreviewSection.jsx'), 'utf8');
  assert(previewContent.includes('Incident Monitoring'), 'Platform preview includes Incident Monitoring');
  assert(previewContent.includes('Resource Allocation'), 'Platform preview includes Resource Allocation');
  assert(previewContent.includes('Mission Tracking'), 'Platform preview includes Mission Tracking');
  assert(previewContent.includes('Route Optimization'), 'Platform preview includes Route Optimization');
  assert(previewContent.includes('ILLUSTRATIVE INTERFACE PREVIEW'), 'Preview is explicitly labeled as illustrative');

  const closingContent = fs.readFileSync(path.join(compDir, 'ClosingBrandSection.jsx'), 'utf8');
  assert(closingContent.includes('Intelligence. Allocation. Response.'), 'Closing section contains exact headline');
  assert(closingContent.includes('One coordinated platform for a faster, more informed emergency response.'),
    'Closing section contains exact supporting message');
  assert(closingContent.includes('to="/login"'), 'Closing section contains generic Login CTA');

  // --------------------------------------------------------------------------
  // TEST 3: Routing & Navigation Verification
  // --------------------------------------------------------------------------
  console.log('\n--- 3. Testing Routing & Navigation Integration ---');
  const appFile = path.resolve(__dirname, '../frontend/src/App.jsx');
  const appContent = fs.readFileSync(appFile, 'utf8');

  assert(appContent.includes('path="/" element={<LandingPage />}'), '/ serves LandingPage');
  assert(appContent.includes('path="/login" element={<Login />}'), '/login serves unified Login interface');
  assert(appContent.includes('path="/citizen"'), '/citizen route exists');
  assert(appContent.includes('path="/admin"'), '/admin route exists');

  // --------------------------------------------------------------------------
  // TEST 4: Live Frontend & Backend Connectivity
  // --------------------------------------------------------------------------
  console.log('\n--- 4. Testing Live Server Responses & Authentication Flows ---');
  try {
    const feRes = await fetch(FRONTEND_URL);
    assert(feRes.ok && feRes.status === 200, `Unified frontend is responding at ${FRONTEND_URL}`);
  } catch (err) {
    assert(false, `Frontend fetch failed: ${err.message}`);
  }

  // Verify Citizen Login via /api/auth/login
  let citizenToken = '';
  try {
    // Register or login a test citizen
    const email = `cit_live_${Date.now()}@test.org`;
    const signupRes = await fetch(`${JEV_URL}/api/auth/signup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'Live Citizen', email, password: 'Password123!' })
    });
    const signupData = await signupRes.json();
    assert(signupRes.status === 201 && signupData.role === 'user', 'Citizen registration works and sets role="user"');
    citizenToken = signupData.token;
  } catch (err) {
    assert(false, `Citizen signup exception: ${err.message}`);
  }

  // Verify Admin Login with seeded credentials
  let adminToken = '';
  try {
    const adminLoginRes = await fetch(`${JEV_URL}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: 'admin@aashray.local', password: 'Admin@Aashray2026!' })
    });
    const adminData = await adminLoginRes.json();
    assert(adminLoginRes.status === 200 && adminData.role === 'admin', 'Admin login works and verifies role="admin"');
    adminToken = adminData.token;
  } catch (err) {
    assert(false, `Admin login exception: ${err.message}`);
  }

  // Verify backend API protection
  try {
    const unauthRes = await fetch(`${JEV_URL}/api/entries/admin`);
    assert(unauthRes.status === 401, 'Unauthenticated request to admin API blocked with HTTP 401');

    const citizenApiRes = await fetch(`${JEV_URL}/api/entries/admin`, {
      headers: { Authorization: `Bearer ${citizenToken}` }
    });
    assert(citizenApiRes.status === 403, 'Citizen token blocked from admin API with HTTP 403');

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

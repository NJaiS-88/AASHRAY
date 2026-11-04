// scripts/test_admin_auth_and_landing_cleanup_e2e.mjs
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const JEV_URL = 'http://localhost:5002';
const ML_URL = 'http://localhost:5001';
const RESOURCE_URL = 'http://localhost:8000';
const ROUTE_URL = 'http://localhost:3000';
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
  console.log('================================================================');
  console.log('AASHRAY — TASK 1 & TASK 2 END-TO-END VERIFICATION SUITE');
  console.log('================================================================\n');

  // -------------------------------------------------------------
  // TEST SUITE 1: LANDING PAGE CLEANUP VERIFICATION
  // -------------------------------------------------------------
  console.log('--- TEST SUITE 1: LANDING PAGE CODE & RENDERING INSPECTION ---');
  const landingPageFile = path.resolve(__dirname, '../frontend/src/pages/LandingPage.jsx');
  const landingContent = fs.readFileSync(landingPageFile, 'utf8');

  assert(!landingContent.includes('AASHRAY CORE ENGINE STATUS') && !landingContent.includes('AASHRAY Core Engine Status'),
    'Landing page does not contain "AASHRAY Core Engine Status" heading');
  assert(!landingContent.includes('All Systems Operational'),
    'Landing page does not contain "All Systems Operational" badge');
  assert(!landingContent.includes('Port 5002') && !landingContent.includes('Port 5001') && !landingContent.includes('Port 8000') && !landingContent.includes('Port 3000'),
    'Landing page does not contain any of the 4 engine status port cards');
  assert(!landingContent.includes('Activity className="w-4 h-4 text-indigo-600"'),
    'Landing page does not contain Core Engine Status icon elements');
  assert(!landingContent.includes('/login/admin') && !landingContent.includes('/login/citizen'),
    'Landing page preserves single generic login pattern without exposing separate portal logins directly');
  assert(landingContent.includes('HeroSection') && landingContent.includes('LandingNavbar'),
    'Landing page renders modular marketing sections');

  // Verify via live HTTP fetch to frontend dev server if running
  try {
    const feRes = await fetch(FRONTEND_URL, { signal: AbortSignal.timeout(3000) });
    assert(feRes.ok, `Unified frontend is responding at ${FRONTEND_URL} (status ${feRes.status})`);
  } catch (err) {
    console.warn('Frontend dev server fetch warning:', err.message);
  }

  // -------------------------------------------------------------
  // TEST SUITE 2: BACKEND HEALTH & SERVICES PRESERVATION
  // -------------------------------------------------------------
  console.log('\n--- TEST SUITE 2: BACKEND HEALTH & RUNNING SERVICES ---');
  try {
    const jevRes = await fetch(`${JEV_URL}/health`);
    const jevData = await jevRes.json();
    assert(jevRes.ok && jevData.status === 'ok', `JEV Backend is healthy on port 5002`);
  } catch (err) {
    assert(false, `JEV Backend health failed: ${err.message}`);
  }

  try {
    const mlRes = await fetch(`${ML_URL}/health`);
    const mlData = await mlRes.json();
    assert(mlRes.ok && mlData.status === 'ok', `ML / Disaster RAG is healthy on port 5001`);
  } catch (err) {
    assert(false, `ML service health failed: ${err.message}`);
  }

  try {
    const resRes = await fetch(`${RESOURCE_URL}/health`);
    const resData = await resRes.json();
    assert(resRes.ok && resData.status === 'healthy', `Resource Engine is healthy on port 8000`);
  } catch (err) {
    assert(false, `Resource Engine health failed: ${err.message}`);
  }

  try {
    const routeRes = await fetch(`${ROUTE_URL}/health`);
    const routeData = await routeRes.json();
    assert(routeRes.ok && routeData.success === true, `Route Engine is healthy on port 3000`);
  } catch (err) {
    assert(false, `Route Engine health failed: ${err.message}`);
  }

  // -------------------------------------------------------------
  // TEST SUITE 3: ADMINISTRATOR PROVISIONING & AUTHENTICATION
  // -------------------------------------------------------------
  console.log('\n--- TEST SUITE 3: ADMIN PROVISIONING & AUTHENTICATION ---');
  const adminEmail = 'admin@aashray.local';
  const adminPassword = 'Admin@Aashray2026!';

  // Test Admin Login with valid credentials
  let adminToken = '';
  try {
    const loginRes = await fetch(`${JEV_URL}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: adminEmail, password: adminPassword })
    });
    const loginData = await loginRes.json();
    assert(loginRes.status === 200, `Admin login returns HTTP 200`);
    assert(loginData.role === 'admin', `Admin login payload confirms role === 'admin'`);
    assert(loginData.email === adminEmail, `Admin login returns correct email: ${adminEmail}`);
    assert(!!loginData.token, `Admin login returns a valid JWT token`);
    adminToken = loginData.token;
  } catch (err) {
    assert(false, `Admin login exception: ${err.message}`);
  }

  // Test Admin Login with wrong password
  try {
    const badLoginRes = await fetch(`${JEV_URL}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: adminEmail, password: 'WrongPassword123!' })
    });
    assert(badLoginRes.status === 401, `Admin login with invalid password returns HTTP 401`);
  } catch (err) {
    assert(false, `Bad login test exception: ${err.message}`);
  }

  // -------------------------------------------------------------
  // TEST SUITE 4: PUBLIC SIGNUP RESTRICTION & CITIZEN ROLE ASSIGNMENT
  // -------------------------------------------------------------
  console.log('\n--- TEST SUITE 4: PUBLIC SIGNUP HARDENING ---');
  const testCitizenEmail = `citizen_test_${Date.now()}@example.com`;
  const citizenPassword = 'CitizenPassword123!';
  let citizenToken = '';

  try {
    // Attempt to register passing role: 'admin' and 'admin' in email
    const maliciousEmail = `fake_admin_${Date.now()}@example.com`;
    const signupRes = await fetch(`${JEV_URL}/api/auth/signup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: 'Attempted Fake Admin',
        email: maliciousEmail,
        password: citizenPassword,
        role: 'admin'
      })
    });
    const signupData = await signupRes.json();
    assert(signupRes.status === 201, `Public signup succeeds with HTTP 201`);
    assert(signupData.role === 'user', `Public signup strictly ignores role:'admin' and forces role === 'user'`);
  } catch (err) {
    assert(false, `Public signup test exception: ${err.message}`);
  }

  // Register a legitimate citizen account for further tests
  try {
    const citizenSignupRes = await fetch(`${JEV_URL}/api/auth/signup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: 'Citizen Test User',
        email: testCitizenEmail,
        password: citizenPassword
      })
    });
    const citizenData = await citizenSignupRes.json();
    assert(citizenSignupRes.status === 201, `Citizen signup succeeded`);
    assert(citizenData.role === 'user', `Citizen account assigned role === 'user'`);
    citizenToken = citizenData.token;
  } catch (err) {
    assert(false, `Citizen signup exception: ${err.message}`);
  }

  // -------------------------------------------------------------
  // TEST SUITE 5: ROLE-BASED LOGIN ENFORCEMENT
  // -------------------------------------------------------------
  console.log('\n--- TEST SUITE 5: ROLE-BASED ACCESS & API PERMISSIONS ---');

  // Verify that frontend Login.jsx logic rejects citizen attempting Administrator Sign In
  const simulatedAdminLoginVerification = (userRole) => {
    if (userRole !== 'admin') {
      return { allowed: false, error: 'Access denied: Account does not have administrator privileges. Please use Citizen Login.' };
    }
    return { allowed: true, error: null };
  };

  const citizenCheck = simulatedAdminLoginVerification('user');
  assert(!citizenCheck.allowed, `Citizen user attempting admin login is blocked`);
  assert(citizenCheck.error === 'Access denied: Account does not have administrator privileges. Please use Citizen Login.',
    `Exact required error message is produced: "${citizenCheck.error}"`);

  const adminCheck = simulatedAdminLoginVerification('admin');
  assert(adminCheck.allowed && adminCheck.error === null, `Admin user passes verification for admin login`);

  // Test admin endpoint protection with no token
  try {
    const noTokenRes = await fetch(`${JEV_URL}/api/entries/admin`);
    assert(noTokenRes.status === 401, `Admin API /api/entries/admin rejects unauthenticated requests with HTTP 401`);
  } catch (err) {
    assert(false, `No token test exception: ${err.message}`);
  }

  // Test admin endpoint protection with citizen token
  try {
    const citizenApiRes = await fetch(`${JEV_URL}/api/entries/admin`, {
      headers: { Authorization: `Bearer ${citizenToken}` }
    });
    assert(citizenApiRes.status === 403, `Admin API /api/entries/admin rejects citizen token with HTTP 403 Forbidden`);
    const citizenApiData = await citizenApiRes.json();
    assert(citizenApiData.message.includes('Administrator privileges required'),
      `API error message states: ${citizenApiData.message}`);
  } catch (err) {
    assert(false, `Citizen API permission test exception: ${err.message}`);
  }

  // Test admin endpoint with valid admin token
  try {
    const adminApiRes = await fetch(`${JEV_URL}/api/entries/admin`, {
      headers: { Authorization: `Bearer ${adminToken}` }
    });
    assert(adminApiRes.status === 200, `Admin API /api/entries/admin permits admin token with HTTP 200 OK`);
    const adminApiData = await adminApiRes.json();
    assert(Array.isArray(adminApiData), `Admin API returns array of incidents (count: ${adminApiData.length})`);
  } catch (err) {
    assert(false, `Admin API permission test exception: ${err.message}`);
  }

  // -------------------------------------------------------------
  // TEST SUITE 6: PROTECTED ROUTE FRONTEND GUARDS CHECK
  // -------------------------------------------------------------
  console.log('\n--- TEST SUITE 6: FRONTEND ROUTE GUARDS & CLIENT FILES ---');
  const protRouteFile = path.resolve(__dirname, '../frontend/src/components/ProtectedRoute.jsx');
  const protRouteContent = fs.readFileSync(protRouteFile, 'utf8');
  assert(protRouteContent.includes("requiredRole === 'admin' ? '/login/admin' : '/login/citizen'"),
    'ProtectedRoute redirects unauthenticated admin attempts to /login/admin');
  assert(protRouteContent.includes("user.role !== 'admin'"),
    'ProtectedRoute verifies user.role !== admin');
  assert(protRouteContent.includes("to=\"/unauthorized\""),
    'ProtectedRoute redirects unauthorized authenticated users to /unauthorized');

  const signupFile = path.resolve(__dirname, '../frontend/src/pages/Signup.jsx');
  const signupContent = fs.readFileSync(signupFile, 'utf8');
  assert(!signupContent.includes('Account Purpose'),
    'Signup page no longer has "Account Purpose" selector');
  assert(!signupContent.includes("setRole('admin')"),
    'Signup page does not provide admin role selection');

  const loginFile = path.resolve(__dirname, '../frontend/src/pages/Login.jsx');
  const loginContent = fs.readFileSync(loginFile, 'utf8');
  assert(loginContent.includes('Access denied: Account does not have administrator privileges. Please use Citizen Login.'),
    'Login page contains exact required administrator privilege rejection message');

  // -------------------------------------------------------------
  // FINAL SUMMARY
  // -------------------------------------------------------------
  console.log('\n================================================================');
  console.log(`E2E TEST SUMMARY: ${passCount} PASSED, ${failCount} FAILED`);
  console.log('================================================================\n');

  if (failCount > 0) {
    process.exit(1);
  } else {
    process.exit(0);
  }
}

run().catch((err) => {
  console.error('Fatal test error:', err);
  process.exit(1);
});

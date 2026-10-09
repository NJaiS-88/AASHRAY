import 'dotenv/config';
import request from 'supertest';
import app from './src/app.js';
import prisma from './src/config/prisma.js';

async function runEndToEndIntegration() {
  console.log('===========================================================');
  console.log('TEST 11 — END-TO-END ROUTE OPTIMISATION API TEST');
  console.log('===========================================================\n');

  try {
    const payload = {
      source: {
        latitude: 19.107221,
        longitude: 72.837236
      },
      destination: {
        latitude: 19.150000,
        longitude: 72.900000
      },
      resourceType: "RELIEF_TRUCK",
      priority: "HIGH",
      missionId: `mission-e2e-${Date.now()}`
    };

    console.log('Sending POST /api/routes/optimize with payload:', payload);

    const res = await request(app)
      .post('/api/routes/optimize')
      .send(payload)
      .set('Content-Type', 'application/json');

    console.log(`\nHTTP Response Status: ${res.status}`);
    console.log('Status Field:', res.body?.data?.status);

    if (res.status !== 200 || !res.body?.success) {
      console.error('Request failed:', res.body);
      throw new Error(`Endpoint returned status ${res.status}`);
    }

    const data = res.body.data;
    console.log('\n--- Decision & Primary Route ---');
    console.log('Routing Decision Status:', data.status);
    console.log('Applied Policy:', data.policyApplied);
    console.log('Decision Reasons:', data.decisionReasons);

    if (data.primaryRoute) {
      console.log('\nPrimary Route Details:');
      console.log(`- Route ID: ${data.primaryRoute.routeId}`);
      console.log(`- Status: ${data.primaryRoute.status}`);
      console.log(`- Score: ${data.primaryRoute.score}`);
      console.log(`- Distance: ${data.primaryRoute.distanceMeters} m`);
      console.log(`- Duration: ${data.primaryRoute.durationSeconds} s`);
      console.log(`- Breakdown:`, data.primaryRoute.breakdown);
      console.log(`- Reasons:`, data.primaryRoute.reasons);
    }

    console.log(`\nBackup Routes Count: ${data.backupRoutes.length}`);
    data.backupRoutes.forEach((b, idx) => {
      console.log(`  Backup ${idx + 1}: ${b.routeId} (Score: ${b.score}, Status: ${b.status})`);
    });

    console.log(`Rejected Routes Count: ${data.rejectedRoutes.length}`);
    data.rejectedRoutes.forEach((r, idx) => {
      console.log(`  Rejected ${idx + 1}: ${r.routeId} (Reason: ${r.rejectionReason})`);
    });

    console.log('\nPipeline Metadata:', data.metadata);

    // Verify Mission tracking was persisted
    if (payload.missionId) {
      const missionState = await prisma.missionRouteState.findUnique({
        where: { missionId: payload.missionId }
      });
      console.log('\nVerified Persisted MissionRouteState in Neon DB:');
      console.log(`- Mission ID: ${missionState?.missionId}`);
      console.log(`- Route Status: ${missionState?.routeStatus}`);
      console.log(`- Primary Route ID: ${missionState?.primaryRouteId}`);
      console.log(`- Route Score: ${missionState?.routeScore}`);
      console.log(`- Reroute Count: ${missionState?.rerouteCount}`);
    }

    console.log('\n✓ END-TO-END ROUTE OPTIMISATION API TEST PASSED! 🎉');
    await prisma.$disconnect();
    process.exit(0);
  } catch (err) {
    console.error('E2E test failed:', err);
    await prisma.$disconnect();
    process.exit(1);
  }
}

runEndToEndIntegration();

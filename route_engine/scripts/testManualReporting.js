import 'dotenv/config';
import request from 'supertest';
import app from '../src/app.js';
import prisma from '../src/config/prisma.js';

async function runManualReportingTests() {
  console.log('=============================================');
  console.log('TESTING MANUAL ROAD-CONDITION REPORTING APIS');
  console.log('=============================================\n');

  try {
    // 1. Citizen Report
    console.log('1. Submitting Citizen report...');
    const citizenPayload = {
      latitude: 19.108500,
      longitude: 72.838500,
      conditionType: 'FLOODED',
      severity: 'HIGH',
      description: 'Water accumulation near underpass'
    };

    const citizenRes = await request(app)
      .post('/api/reports/citizen')
      .send(citizenPayload)
      .set('Content-Type', 'application/json');

    console.log(`Citizen response status: ${citizenRes.status}`);
    console.log('Citizen response data:', citizenRes.body);
    if (citizenRes.status !== 201) {
      throw new Error('Citizen report failed');
    }

    // 2. Responder Report WITHOUT proper authorization (should be 403 Forbidden)
    console.log('\n2. Submitting Responder report as unprivileged user (expecting 403 Forbidden)...');
    const responderPayload = {
      latitude: 19.109200,
      longitude: 72.839000,
      conditionType: 'ROAD_BLOCKED',
      severity: 'CRITICAL',
      vehiclePassable: false,
      description: 'Downed tree completely blocking lane'
    };

    const unauthorizedRes = await request(app)
      .post('/api/reports/responder')
      .send(responderPayload)
      .set('Content-Type', 'application/json');

    console.log(`Unauthorized responder response status: ${unauthorizedRes.status}`);
    if (unauthorizedRes.status !== 403) {
      throw new Error(`Expected 403 Forbidden, but received ${unauthorizedRes.status}`);
    }
    console.log('✓ Successfully blocked unprivileged user from submitting responder report');

    // 3. Responder Report WITH proper authorization (x-user-role: RESPONDER)
    console.log('\n3. Submitting Responder report with RESPONDER credentials...');
    const authorizedRes = await request(app)
      .post('/api/reports/responder')
      .send(responderPayload)
      .set('x-user-id', 'responder-unit-42')
      .set('x-user-role', 'RESPONDER')
      .set('Content-Type', 'application/json');

    console.log(`Authorized responder response status: ${authorizedRes.status}`);
    console.log('Authorized responder data:', authorizedRes.body);
    if (authorizedRes.status !== 201) {
      throw new Error('Authorized responder report failed');
    }

    // 4. Verify records in database
    console.log('\n4. Verifying stored records in database...');
    const citizenRecord = await prisma.roadConditionEvidence.findUnique({
      where: { id: citizenRes.body.data.evidenceId }
    });
    const responderRecord = await prisma.roadConditionEvidence.findUnique({
      where: { id: authorizedRes.body.data.evidenceId }
    });

    console.log('Citizen Record in DB:', {
      id: citizenRecord.id,
      source: citizenRecord.source,
      conditionType: citizenRecord.conditionType,
      status: citizenRecord.status,
      confidence: citizenRecord.confidence
    });

    console.log('Responder Record in DB:', {
      id: responderRecord.id,
      source: responderRecord.source,
      conditionType: responderRecord.conditionType,
      status: responderRecord.status,
      confidence: responderRecord.confidence
    });

    console.log('\nALL MANUAL REPORTING API TESTS PASSED! 🎉');
    await prisma.$disconnect();
    process.exit(0);
  } catch (err) {
    console.error('Test error:', err);
    await prisma.$disconnect();
    process.exit(1);
  }
}

runManualReportingTests();

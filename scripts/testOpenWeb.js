import { getRoadIncidents } from '../src/services/openWeb.service.js';
import dotenv from 'dotenv';
import path from 'path';

// Override config with local environment variables before executing test
dotenv.config({ path: path.resolve(process.cwd(), '.env') });
import { config } from '../src/config/env.js';
config.openWebNinjaApiKey = process.env.OPENWEBNINJA_API_KEY;

async function runTest() {
  const TARGET_LAT = 19.107221;
  const TARGET_LON = 72.837236;
  
  const params = {
    bottomLeft: "19.087221,72.817236",
    topRight: "19.127221,72.857236"
  };

  console.log("\n======================================");
  console.log("WAZE EXACT-LOCATION TEST (REFACTORED)");
  console.log("======================================");
  console.log("Target:", TARGET_LAT, TARGET_LON);
  console.log("Bounding Box:", params);
  
  try {
    const incidents = await getRoadIncidents(params);
    console.log(`\nFound ${incidents.length} total incidents in bounding box.`);
    
    const roadClosures = incidents.filter(i => i.type === 'ROAD_CLOSED');
    console.log(`\nFound ${roadClosures.length} ROAD_CLOSED incidents.\n`);
    
    roadClosures.forEach((closure, index) => {
      console.log(`----- CLOSURE ${index + 1} -----`);
      console.log(`Street: ${closure.street} (${closure.city})`);
      console.log(`External ID: ${closure.externalId}`);
      console.log(`Age: ${closure.dataAgeSeconds} seconds (${closure.freshness})`);
      console.log(`Confidence: ${closure.confidence}`);
      console.log(`Speed: ${closure.speedKmh} km/h`);
      console.log(`Severity: ${closure.severityLevel}`);
      console.log(`Details: ${JSON.stringify(closure, null, 2)}\n`);
    });
    
  } catch (err) {
    console.error("❌ Test failed:", err.message);
    if (err.response) {
       console.error("Status:", err.response.status);
       console.error(err.response.data);
    }
  }
}

runTest();

import 'dotenv/config';
import { getCandidateRoutes } from './src/services/googleRoutes.service.js';

async function testGoogleRoutes() {
  console.log('Testing Google Routes API Service...');
  try {
    const origin = { latitude: 19.107221, longitude: 72.837236 };
    const destination = { latitude: 19.150000, longitude: 72.900000 };
    
    console.log(`Requesting routes from ${origin.latitude},${origin.longitude} to ${destination.latitude},${destination.longitude}`);
    
    const routes = await getCandidateRoutes({ origin, destination });
    
    console.log(`\nSuccessfully received ${routes.length} candidate routes!`);
    console.log('\nNormalized Routes:');
    console.dir(routes, { depth: null });
  } catch (error) {
    console.error('Test failed:', error);
  }
}

testGoogleRoutes();

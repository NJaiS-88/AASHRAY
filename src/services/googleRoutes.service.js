import axios from 'axios';

const GOOGLE_ROUTES_API_URL = 'https://routes.googleapis.com/directions/v2:computeRoutes';

/**
 * Fetches route alternatives from Google Routes API
 * @param {Object} params 
 * @param {Object} params.origin { latitude, longitude }
 * @param {Object} params.destination { latitude, longitude }
 * @returns {Promise<Array>} Array of normalized route objects
 */
export const getCandidateRoutes = async ({ origin, destination }) => {
  const apiKey = process.env.GOOGLE_MAPS_API_KEY;
  if (!apiKey) {
    throw new Error('GOOGLE_MAPS_API_KEY is not defined in environment variables');
  }

  const requestBody = {
    origin: {
      location: {
        latLng: {
          latitude: origin.latitude,
          longitude: origin.longitude
        }
      }
    },
    destination: {
      location: {
        latLng: {
          latitude: destination.latitude,
          longitude: destination.longitude
        }
      }
    },
    travelMode: 'DRIVE',
    routingPreference: 'TRAFFIC_AWARE',
    computeAlternativeRoutes: true
  };

  try {
    const response = await axios.post(GOOGLE_ROUTES_API_URL, requestBody, {
      headers: {
        'Content-Type': 'application/json',
        'X-Goog-Api-Key': apiKey,
        'X-Goog-FieldMask': 'routes.distanceMeters,routes.duration,routes.polyline.encodedPolyline,routes.description,routes.warnings,routes.routeLabels'
      },
      timeout: 10000 // 10 seconds timeout
    });

    const routes = response.data.routes || [];

    // Normalize routes
    return routes.map((route, index) => {
      return {
        routeId: `google-route-${index}`,
        distanceMeters: parseInt(route.distanceMeters, 10),
        durationSeconds: route.duration ? parseInt(route.duration.replace('s', ''), 10) : 0,
        encodedPolyline: route.polyline?.encodedPolyline,
        routeLabels: route.routeLabels || [],
        description: route.description || ''
      };
    });
  } catch (error) {
    console.error('Error fetching routes from Google Routes API:', error.response?.data || error.message);
    throw new Error('Failed to compute routes from Google Routes API');
  }
};

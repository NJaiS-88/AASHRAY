import * as turf from '@turf/turf';
import polyline from '@mapbox/polyline';

/**
 * Default geographic corridor / tolerance in meters.
 * E.g., 50 meters from route centerline.
 */
export const DEFAULT_CORRIDOR_METERS = 50;

/**
 * Decodes Google encoded polyline and converts to GeoJSON Feature<LineString>.
 * Note: Google polyline decodes to [latitude, longitude].
 * GeoJSON requires coordinates in [longitude, latitude] order.
 * 
 * @param {string} encodedPolyline 
 * @returns {import('@turf/turf').Feature<import('@turf/turf').LineString>}
 */
export function decodePolylineToGeoJSON(encodedPolyline) {
  if (!encodedPolyline || typeof encodedPolyline !== 'string') {
    throw new Error('Valid encodedPolyline string is required');
  }

  // polyline.decode returns [[lat, lng], [lat, lng], ...]
  const decodedCoords = polyline.decode(encodedPolyline);

  if (decodedCoords.length < 2) {
    throw new Error('Decoded polyline must have at least 2 points to form a LineString');
  }

  // Convert to GeoJSON [lng, lat]
  const coordinates = decodedCoords.map(([lat, lng]) => [lng, lat]);

  return turf.lineString(coordinates);
}

/**
 * Converts an incident or evidence record into a GeoJSON geometry.
 * If lineCoordinates exists and has >= 2 points, returns Feature<LineString>.
 * Otherwise, if coordinates or latitude/longitude exist, returns Feature<Point>.
 * 
 * @param {Object} incident 
 * @returns {import('@turf/turf').Feature | null}
 */
export function incidentToGeoJSON(incident) {
  // Check for lineCoordinates (either direct property or inside rawMetadata)
  const lineCoords = incident.lineCoordinates || 
    (incident.rawMetadata && incident.rawMetadata.lineCoordinates);

  if (Array.isArray(lineCoords) && lineCoords.length >= 2) {
    const geoJsonCoords = lineCoords
      .map(pt => {
        const lat = pt.lat ?? pt.latitude;
        const lon = pt.lon ?? pt.lng ?? pt.longitude;
        if (typeof lat === 'number' && typeof lon === 'number') {
          return [lon, lat];
        }
        return null;
      })
      .filter(Boolean);

    if (geoJsonCoords.length >= 2) {
      return turf.lineString(geoJsonCoords);
    }
  }

  // Point coordinates
  const lat = incident.latitude ?? (incident.rawMetadata?.coordinates?.latitude);
  const lon = incident.longitude ?? (incident.rawMetadata?.coordinates?.longitude);

  if (typeof lat === 'number' && typeof lon === 'number') {
    return turf.point([lon, lat]);
  }

  return null;
}

/**
 * Calculates shortest distance between an incident geometry and a route line.
 * Turf distance is in kilometers or meters.
 * 
 * @param {import('@turf/turf').Feature} incidentGeo 
 * @param {import('@turf/turf').Feature<import('@turf/turf').LineString>} routeLine 
 * @returns {number} distance in meters
 */
export function calculateDistanceToRoute(incidentGeo, routeLine) {
  if (!incidentGeo || !routeLine) return Infinity;

  const geomType = incidentGeo.geometry.type;

  if (geomType === 'Point') {
    // pointToLineDistance returns distance in units (default km)
    const distanceKm = turf.pointToLineDistance(incidentGeo, routeLine, { units: 'kilometers' });
    return distanceKm * 1000;
  }

  if (geomType === 'LineString') {
    // Check if the lines intersect directly
    const intersects = turf.lineIntersect(incidentGeo, routeLine);
    if (intersects.features.length > 0) {
      return 0;
    }

    // Otherwise calculate minimum distance between sampled vertices
    let minDistanceKm = Infinity;
    const incidentCoords = incidentGeo.geometry.coordinates;
    for (const coord of incidentCoords) {
      const pt = turf.point(coord);
      const d = turf.pointToLineDistance(pt, routeLine, { units: 'kilometers' });
      if (d < minDistanceKm) {
        minDistanceKm = d;
      }
    }
    return minDistanceKm * 1000;
  }

  return Infinity;
}

/**
 * Evaluates whether an incident affects a candidate route based on corridor tolerance.
 * 
 * @param {Object} incident - Incident or stored RoadConditionEvidence object
 * @param {import('@turf/turf').Feature<import('@turf/turf').LineString>} routeLine
 * @param {number} toleranceMeters
 * @param {string} routeId
 * @returns {Object|null} Match details if affected, null otherwise
 */
export function matchIncidentToRoute(incident, routeLine, toleranceMeters = DEFAULT_CORRIDOR_METERS, routeId = 'unknown') {
  const geo = incidentToGeoJSON(incident);
  if (!geo) return null;

  const distanceMeters = calculateDistanceToRoute(geo, routeLine);

  if (distanceMeters <= toleranceMeters) {
    const isClosed = incident.conditionType === 'ROAD_CLOSED' || 
                     incident.blockAlertType === 'ROAD_CLOSED' ||
                     incident.type === 'ROAD_CLOSED' ||
                     incident.rawMetadata?.blockAlertType === 'ROAD_CLOSED';

    return {
      incidentId: incident.id || incident.externalId || incident.rawMetadata?.externalId || 'unknown',
      externalId: incident.externalId || incident.rawMetadata?.externalId || null,
      source: incident.source || 'OPENWEB_NINJA',
      provider: incident.provider || incident.rawMetadata?.provider || 'WAZE',
      conditionType: isClosed ? 'ROAD_CLOSED' : (incident.conditionType || incident.type || 'OTHER'),
      status: isClosed ? 'BLOCKED' : (incident.status || 'RISKY'),
      street: incident.street || incident.rawMetadata?.street || null,
      distanceFromRouteMeters: Math.round(distanceMeters * 10) / 10,
      matchedRoute: routeId,
      confidence: incident.confidence || 'UNKNOWN',
      isBlocking: isClosed
    };
  }

  return null;
}

/**
 * Matches candidate routes against a collection of road incidents.
 * 
 * @param {Array<Object>} candidateRoutes - Routes from Google Routes API with encodedPolyline
 * @param {Array<Object>} incidents - Incidents from OpenWeb or RoadConditionEvidence records
 * @param {Object} [options]
 * @param {number} [options.toleranceMeters=DEFAULT_CORRIDOR_METERS] - Buffer tolerance in meters
 * @returns {Array<Object>} Candidate routes enriched with matched incidents and affected flag
 */
export function matchRoutesWithConditions(candidateRoutes, incidents, options = {}) {
  const toleranceMeters = options.toleranceMeters || DEFAULT_CORRIDOR_METERS;

  if (!Array.isArray(candidateRoutes)) return [];
  if (!Array.isArray(incidents) || incidents.length === 0) {
    return candidateRoutes.map(route => ({
      ...route,
      affected: false,
      blockingCondition: null,
      matchedIncidents: []
    }));
  }

  return candidateRoutes.map((route, idx) => {
    const routeId = route.routeId || `route-${idx}`;

    if (!route.encodedPolyline) {
      return {
        ...route,
        affected: false,
        blockingCondition: null,
        matchedIncidents: []
      };
    }

    try {
      const routeLine = decodePolylineToGeoJSON(route.encodedPolyline);
      const matchedIncidents = [];
      let isBlocked = false;
      let blockingCondition = null;

      for (const incident of incidents) {
        const match = matchIncidentToRoute(incident, routeLine, toleranceMeters, routeId);
        if (match) {
          matchedIncidents.push(match);
          if (match.isBlocking) {
            isBlocked = true;
            blockingCondition = match.conditionType;
          }
        }
      }

      return {
        ...route,
        affected: matchedIncidents.length > 0,
        isBlocked,
        blockingCondition: isBlocked ? blockingCondition : (matchedIncidents.length > 0 ? matchedIncidents[0].conditionType : null),
        matchedIncidents
      };
    } catch (err) {
      console.warn(`Failed to process route ${routeId} polyline:`, err.message);
      return {
        ...route,
        affected: false,
        blockingCondition: null,
        matchedIncidents: []
      };
    }
  });
}

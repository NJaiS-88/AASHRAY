import { getCandidateRoutes } from './googleRoutes.service.js';
import { getRoadIncidents } from './openWeb.service.js';
import { storeRoadConditionEvidences } from './evidenceStorage.service.js';
import { matchRoutesWithConditions } from './routeConditionMatcher.service.js';
import { evaluateRoadConditions } from './roadConditionEngine.service.js';
import { getResourcePolicy } from './resourceRiskPolicy.service.js';
import { scoreCandidateRoutes } from './routeScoring.service.js';
import { selectRoutes } from './routeSelection.service.js';
import { persistMissionRouteState } from './missionTracking.service.js';
import { calculateBoundingBox } from '../utils/geoUtils.js';
import polyline from '@mapbox/polyline';

/**
 * End-to-end Disaster-Aware Route Optimization Pipeline
 * 
 * Flow:
 * 1. Retrieve Google candidate routes (with alternative routes computation).
 * 2. Calculate geographic bounding box covering origin, destination, and all candidate polylines.
 * 3. Fetch real-time road-condition incidents via OpenWeb Ninja (openWeb.service.js).
 * 4. Normalize and store road-condition evidence in PostgreSQL database.
 * 5. Perform geographic matching between candidate route polylines and road incidents.
 * 6. Run Road Condition Engine evaluation per candidate route.
 * 7. Retrieve Resource and Vehicle Risk Policy (travelTimeWeight, roadRiskWeight, uncertaintyWeight).
 * 8. Deterministically score each route (relative travel time, road risk, uncertainty).
 * 9. Select PRIMARY route (lowest risk penalty) and BACKUP routes; flag INVALID/blocked routes with reasons.
 * 10. Persist route decision in database if missionId is supplied.
 * 11. Return transparent, explainable routing result.
 * 
 * @param {Object} params
 * @param {Object} params.source { latitude, longitude }
 * @param {Object} params.destination { latitude, longitude }
 * @param {string} [params.resourceId]
 * @param {string} [params.resourceType='DEFAULT']
 * @param {string} [params.priority='MEDIUM']
 * @param {string} [params.missionId]
 * @param {Object} [params.options]
 * @param {number} [params.options.corridorToleranceMeters=50]
 * @returns {Promise<Object>} Complete route optimization response
 */
export async function optimizeRoutePipeline({
  source,
  destination,
  resourceId = null,
  resourceType = 'DEFAULT',
  priority = 'MEDIUM',
  missionId = null,
  options = {}
}) {
  // 1. Candidate routes from Google Routes API
  const candidateRoutes = await getCandidateRoutes({
    origin: source,
    destination: destination
  });

  // Extract all coordinates from routes to establish an accurate bounding box
  const allPoints = [];
  for (const r of candidateRoutes) {
    if (r.encodedPolyline) {
      try {
        const decoded = polyline.decode(r.encodedPolyline);
        allPoints.push(...decoded);
      } catch (e) {
        // ignore decode failure for bounding box
      }
    }
  }

  // 2. Determine geographic bounding box
  const bbox = calculateBoundingBox({
    origin: source,
    destination: destination,
    points: allPoints,
    paddingDegrees: 0.03 // ~3.3km buffer
  });

  // 3. OpenWeb Ninja call (single centralized service call)
  let incidents = [];
  try {
    incidents = await getRoadIncidents({
      bottomLeft: bbox.bottomLeft,
      topRight: bbox.topRight
    });
  } catch (err) {
    console.warn('OpenWeb Ninja incidents fetch failed or unavailable:', err.message);
    incidents = [];
  }

  // 4. Store/update road-condition evidence
  let storedEvidences = [];
  if (incidents.length > 0) {
    try {
      storedEvidences = await storeRoadConditionEvidences(incidents);
    } catch (err) {
      console.error('Failed to store road condition evidence:', err.message);
    }
  }

  // 5. Geographic matching with candidate routes
  const toleranceMeters = options.corridorToleranceMeters || 50;
  const matchedRoutes = matchRoutesWithConditions(candidateRoutes, incidents, {
    toleranceMeters
  });

  // 6. Evaluate road condition status per route using Road Condition Engine
  const routesWithAssessments = matchedRoutes.map(route => {
    const evaluation = evaluateRoadConditions(route.matchedIncidents);

    return {
      ...route,
      roadConditionAssessment: {
        status: evaluation.status,
        confidence: evaluation.confidence,
        reasons: evaluation.reasons
      }
    };
  });

  // 7. Get Resource / Vehicle Policy
  const resourcePolicy = getResourcePolicy({ resourceType, priority });

  // 8. Score candidate routes
  const scoredRoutes = scoreCandidateRoutes({
    candidateRoutes: routesWithAssessments,
    policy: resourcePolicy
  });

  // 9. Select primary, backup, and rejected routes
  const selection = selectRoutes({
    scoredRoutes,
    resourcePolicy,
    priority
  });

  // 10. Persist mission route state if missionId provided
  if (missionId) {
    await persistMissionRouteState({
      missionId,
      resourceId,
      resourceType,
      priority,
      source,
      destination,
      selectionResult: selection
    });
  }

  const roadClosuresCount = incidents.filter(i => i.type === 'ROAD_CLOSED' || i.blockAlertType === 'ROAD_CLOSED').length;

  return {
    status: selection.status,
    primaryRoute: selection.primaryRoute,
    backupRoutes: selection.backupRoutes,
    rejectedRoutes: selection.rejectedRoutes,
    decisionReasons: selection.decisionReasons,
    policyApplied: {
      resourceType: resourcePolicy.resourceType,
      priority: resourcePolicy.priority,
      weights: resourcePolicy.weights,
      blockingConfidenceThreshold: resourcePolicy.blockingConfidenceThreshold
    },
    metadata: {
      boundingBox: bbox,
      incidentsReceived: incidents.length,
      roadClosuresCount,
      storedRecordsCount: storedEvidences.length,
      corridorToleranceMeters: toleranceMeters,
      totalCandidateRoutes: candidateRoutes.length,
      validRoutesCount: selection.backupRoutes.length + (selection.primaryRoute ? 1 : 0),
      rejectedRoutesCount: selection.rejectedRoutes.length
    }
  };
}

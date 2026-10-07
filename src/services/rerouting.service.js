import prisma from '../config/prisma.js';
import { getCandidateRoutes } from './googleRoutes.service.js';
import { getRoadIncidents } from './openWeb.service.js';
import { storeRoadConditionEvidences } from './evidenceStorage.service.js';
import { matchRoutesWithConditions } from './routeConditionMatcher.service.js';
import { evaluateRoadConditions } from './roadConditionEngine.service.js';
import { getResourcePolicy } from './resourceRiskPolicy.service.js';
import { scoreCandidateRoutes } from './routeScoring.service.js';
import { selectRoutes } from './routeSelection.service.js';
import { calculateBoundingBox } from '../utils/geoUtils.js';
import polyline from '@mapbox/polyline';

/**
 * Dynamic Re-routing Service
 * 
 * Determines whether an existing active mission route should be recalculated.
 * 
 * Flow:
 * 1. Inspect current active route and origin/destination coordinates.
 * 2. Fetch latest road-condition evidence in the relevant corridor / bounding box.
 * 3. Evaluate the current route against updated conditions.
 * 4. If current route remains acceptable (not BLOCKED by fresh/trusted evidence):
 *      -> return rerouted: false, keep current primary route.
 * 5. If current route becomes affected by a blocking condition (BLOCKED):
 *      -> Request fresh candidate routes.
 *      -> Refresh road conditions and match.
 *      -> Score routes and select new primary + backups.
 *      -> If missionId exists in database, update MissionRouteState.
 *      -> return rerouted: true with new primary and explanation.
 * 
 * IMPORTANT:
 * - Deterministic and explicitly callable (no endless setInterval).
 * - Avoids unnecessary reroutes for low-confidence or distant reports.
 */

/**
 * Evaluates and executes dynamic rerouting if necessary.
 * 
 * @param {Object} params
 * @param {Object} params.currentRoute - The current assigned route object (must have encodedPolyline or routeId)
 * @param {Object} params.source { latitude, longitude }
 * @param {Object} params.destination { latitude, longitude }
 * @param {string} [params.resourceType='DEFAULT']
 * @param {string} [params.priority='MEDIUM']
 * @param {string} [params.missionId] - Optional tracking mission ID
 * @param {Array<Object>} [params.currentBackups=[]] - Existing backup routes
 * @param {number} [params.corridorToleranceMeters=50]
 * @returns {Promise<Object>} Rerouting decision result
 */
export async function evaluateAndReroute({
  currentRoute,
  source,
  destination,
  resourceType = 'DEFAULT',
  priority = 'MEDIUM',
  missionId = null,
  currentBackups = [],
  corridorToleranceMeters = 50
}) {
  const evaluatedAt = new Date().toISOString();

  if (!currentRoute || !source || !destination) {
    throw new Error('currentRoute, source, and destination are required for rerouting evaluation');
  }

  const policy = getResourcePolicy({ resourceType, priority });

  // 1. Determine bounding box for current route
  const currentPoints = [];
  if (currentRoute.encodedPolyline) {
    try {
      currentPoints.push(...polyline.decode(currentRoute.encodedPolyline));
    } catch (e) {
      // polyline decode error ignored
    }
  }

  const bbox = calculateBoundingBox({
    origin: source,
    destination: destination,
    points: currentPoints,
    paddingDegrees: 0.03
  });

  // 2. Fetch latest road conditions from OpenWeb Ninja
  let latestIncidents = [];
  try {
    latestIncidents = await getRoadIncidents({
      bottomLeft: bbox.bottomLeft,
      topRight: bbox.topRight
    });
  } catch (err) {
    console.warn('OpenWeb Ninja incidents fetch failed during reroute check:', err.message);
    latestIncidents = [];
  }

  // 3. Store/update latest evidence in database
  if (latestIncidents.length > 0) {
    try {
      await storeRoadConditionEvidences(latestIncidents);
    } catch (err) {
      console.warn('Failed to update evidence during reroute evaluation:', err.message);
    }
  }

  // Also query recent non-expired database evidence within the vicinity (e.g. Responder/Citizen reports)
  let dbEvidences = [];
  try {
    dbEvidences = await prisma.roadConditionEvidence.findMany({
      where: {
        latitude: { gte: bbox.minLat, lte: bbox.maxLat },
        longitude: { gte: bbox.minLng, lte: bbox.maxLng }
      },
      orderBy: { reportedAt: 'desc' },
      take: 50
    });
  } catch (err) {
    console.warn('Failed to query db evidence during reroute evaluation:', err.message);
  }

  // Combine incidents
  const allRelevantEvidence = [...latestIncidents, ...dbEvidences];

  // 4. Test if CURRENT ROUTE is blocked by any fresh evidence
  const [matchedCurrent] = matchRoutesWithConditions([currentRoute], allRelevantEvidence, {
    toleranceMeters: corridorToleranceMeters
  });

  const currentAssessment = evaluateRoadConditions(matchedCurrent.matchedIncidents);
  const isCurrentBlocked = currentAssessment.status === 'BLOCKED';

  // If current route is NOT blocked, no reroute required
  if (!isCurrentBlocked) {
    // Update last evaluation timestamp if tracking mission
    if (missionId) {
      try {
        await prisma.missionRouteState.updateMany({
          where: { missionId },
          data: { lastRoadConditionEvaluation: new Date() }
        });
      } catch (err) {
        // ignore tracking update failure
      }
    }

    return {
      rerouted: false,
      reason: currentAssessment.status === 'RISKY' 
        ? 'Current route has moderate traffic or risk within policy tolerance, but remains open. No reroute required.'
        : 'Current route remains clear of blocking hazards and road closures.',
      previousRouteId: currentRoute.routeId,
      newPrimaryRoute: currentRoute,
      backupRoutes: currentBackups,
      rejectedRoutes: [],
      evaluatedAt
    };
  }

  // CURRENT ROUTE IS BLOCKED! Reroute required.
  const blockingReason = currentAssessment.reasons.find(r => r.type === 'ROAD_CLOSED' || r.type === 'ROAD_BLOCKED')?.type || 'ROAD_CLOSED';
  console.log(`[REROUTING] Current route ${currentRoute.routeId} is BLOCKED by ${blockingReason}. Computing fresh candidate routes...`);

  // Request fresh candidate routes
  let freshCandidates = [];
  try {
    freshCandidates = await getCandidateRoutes({
      origin: source,
      destination: destination
    });
  } catch (err) {
    console.error('Failed to retrieve fresh candidate routes from Google Routes API:', err.message);
    freshCandidates = [];
  }

  // Match fresh candidate routes against all road conditions
  const matchedFreshRoutes = matchRoutesWithConditions(freshCandidates, allRelevantEvidence, {
    toleranceMeters: corridorToleranceMeters
  });

  // Evaluate and score
  const enrichedFreshRoutes = matchedFreshRoutes.map(r => {
    const assessment = evaluateRoadConditions(r.matchedIncidents);
    return {
      ...r,
      roadConditionAssessment: assessment
    };
  });

  const scoredFreshRoutes = scoreCandidateRoutes({
    candidateRoutes: enrichedFreshRoutes,
    policy
  });

  // Select primary and backups
  const selection = selectRoutes({
    scoredRoutes: scoredFreshRoutes,
    resourcePolicy: policy,
    priority
  });

  // If mission tracking exists, update the database record
  if (missionId) {
    try {
      const existing = await prisma.missionRouteState.findUnique({
        where: { missionId }
      });

      if (existing) {
        await prisma.missionRouteState.update({
          where: { missionId },
          data: {
            routeStatus: selection.status,
            primaryRouteId: selection.primaryRoute?.routeId || null,
            routeScore: selection.primaryRoute?.score ?? null,
            primaryRouteData: selection.primaryRoute ? {
              routeId: selection.primaryRoute.routeId,
              distanceMeters: selection.primaryRoute.distanceMeters,
              durationSeconds: selection.primaryRoute.durationSeconds,
              encodedPolyline: selection.primaryRoute.encodedPolyline,
              score: selection.primaryRoute.score
            } : null,
            backupRoutesData: selection.backupRoutes.map(b => ({
              routeId: b.routeId,
              distanceMeters: b.distanceMeters,
              durationSeconds: b.durationSeconds,
              score: b.score
            })),
            rerouteCount: existing.rerouteCount + 1,
            lastRerouteAt: new Date(),
            lastRoadConditionEvaluation: new Date()
          }
        });
      }
    } catch (err) {
      console.warn('Failed to update MissionRouteState in database during reroute:', err.message);
    }
  }

  return {
    rerouted: true,
    reason: `Reroute triggered: previous route ${currentRoute.routeId} encountered ${blockingReason}. New route selected based on ${resourceType} policy.`,
    previousRouteId: currentRoute.routeId,
    status: selection.status,
    newPrimaryRoute: selection.primaryRoute,
    backupRoutes: selection.backupRoutes,
    rejectedRoutes: selection.rejectedRoutes,
    decisionReasons: selection.decisionReasons,
    evaluatedAt
  };
}

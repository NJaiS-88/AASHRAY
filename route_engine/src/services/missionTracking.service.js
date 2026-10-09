import prisma from '../config/prisma.js';

/**
 * Mission Tracking Integration Service
 * 
 * Provides lightweight tracking state persistence for disaster response missions.
 * Consumes mission parameters from Resource Allocation without owning resource allocation logic.
 */

/**
 * Creates or updates the route tracking state for a mission.
 * 
 * @param {Object} params
 * @param {string} params.missionId
 * @param {string} [params.resourceId]
 * @param {string} [params.resourceType='DEFAULT']
 * @param {string} [params.priority='MEDIUM']
 * @param {Object} params.source { latitude, longitude }
 * @param {Object} params.destination { latitude, longitude }
 * @param {Object} params.selectionResult - Output from selectRoutes
 * @returns {Promise<Object>} Persisted MissionRouteState record
 */
export async function persistMissionRouteState({
  missionId,
  resourceId = null,
  resourceType = 'DEFAULT',
  priority = 'MEDIUM',
  source,
  destination,
  selectionResult
}) {
  if (!missionId) return null;

  const primary = selectionResult.primaryRoute;
  const backups = selectionResult.backupRoutes || [];

  const primaryRouteData = primary ? {
    routeId: primary.routeId,
    distanceMeters: primary.distanceMeters,
    durationSeconds: primary.durationSeconds,
    encodedPolyline: primary.encodedPolyline,
    score: primary.score,
    breakdown: primary.breakdown,
    roadConditionAssessment: primary.roadConditionAssessment
  } : null;

  const backupRoutesData = backups.map(b => ({
    routeId: b.routeId,
    distanceMeters: b.distanceMeters,
    durationSeconds: b.durationSeconds,
    score: b.score,
    breakdown: b.breakdown
  }));

  try {
    const record = await prisma.missionRouteState.upsert({
      where: { missionId },
      create: {
        missionId,
        resourceId,
        resourceType,
        priority,
        sourceLatitude: source.latitude,
        sourceLongitude: source.longitude,
        destinationLatitude: destination.latitude,
        destinationLongitude: destination.longitude,
        routeStatus: selectionResult.status,
        primaryRouteId: primary ? primary.routeId : null,
        routeScore: primary ? primary.score : null,
        primaryRouteData,
        backupRoutesData,
        rerouteCount: 0,
        lastRouteCalculationAt: new Date(),
        lastRoadConditionEvaluation: new Date()
      },
      update: {
        resourceId,
        resourceType,
        priority,
        sourceLatitude: source.latitude,
        sourceLongitude: source.longitude,
        destinationLatitude: destination.latitude,
        destinationLongitude: destination.longitude,
        routeStatus: selectionResult.status,
        primaryRouteId: primary ? primary.routeId : null,
        routeScore: primary ? primary.score : null,
        primaryRouteData,
        backupRoutesData,
        lastRouteCalculationAt: new Date(),
        lastRoadConditionEvaluation: new Date()
      }
    });

    return record;
  } catch (err) {
    console.error('Failed to persist mission route state:', err.message);
    return null;
  }
}

/**
 * Retrieves the current route tracking state for a given mission.
 * 
 * @param {string} missionId 
 * @returns {Promise<Object|null>}
 */
export async function getMissionRouteState(missionId) {
  if (!missionId) return null;
  return await prisma.missionRouteState.findUnique({
    where: { missionId }
  });
}

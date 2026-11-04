/**
 * Route Selection Service
 * 
 * Takes scored candidate routes, filters out INVALID routes,
 * ranks the remaining VALID routes by lowest penalty score,
 * and selects:
 * - primaryRoute (lowest penalty score)
 * - backupRoutes (subsequent valid routes)
 * - rejectedRoutes (all invalid routes with specific rejection reasons)
 * 
 * Handles cases:
 * - 0 routes or 0 valid routes -> status: "NO_SAFE_ROUTE_FOUND"
 * - 1 valid route -> primaryRoute, backupRoutes = []
 * - Multiple valid routes -> primaryRoute + sorted backupRoutes
 * 
 * Never invents fake alternative routes if only 1 exists or if all are invalid.
 */

/**
 * Selects primary and backup routes from scored candidate routes.
 * 
 * @param {Object} params
 * @param {Array<Object>} params.scoredRoutes - Output from scoreCandidateRoutes
 * @param {Object} [params.resourcePolicy]
 * @param {string} [params.priority='MEDIUM']
 * @returns {{
 *   status: 'ROUTE_FOUND' | 'NO_SAFE_ROUTE_FOUND',
 *   primaryRoute: Object | null,
 *   backupRoutes: Array<Object>,
 *   rejectedRoutes: Array<Object>,
 *   decisionReasons: Array<string>
 * }}
 */
export function selectRoutes({ scoredRoutes = [], resourcePolicy = null, priority = 'MEDIUM' } = {}) {
  const rejectedRoutes = [];
  const validRoutes = [];

  for (const route of scoredRoutes) {
    const isUnavailable = route.status === 'UNAVAILABLE' || route.blockingCondition === 'MISSING_GEOMETRY' || route.ruleViolated === 'MISSING_GEOMETRY';
    if (isUnavailable) {
      rejectedRoutes.push({
        routeId: route.routeId,
        status: 'UNAVAILABLE',
        selectionStatus: 'UNAVAILABLE',
        distanceMeters: route.distanceMeters ?? null,
        durationSeconds: route.durationSeconds ?? null,
        encodedPolyline: null,
        score: null,
        blockingCondition: 'MISSING_GEOMETRY',
        evidenceSource: route.evidenceSource || 'ROUTING_PROVIDER',
        confidence: 'HIGH',
        freshness: 'N/A',
        rejectionReason: route.rejectionReason || 'Route geometry or evaluation could not be obtained from routing provider.',
        ruleViolated: 'MISSING_GEOMETRY',
        allReasons: route.reasons || []
      });
    } else if (route.status === 'INVALID' || route.status === 'REJECTED') {
      const primaryRejection = route.rejectionReason || route.reasons?.[0]?.message || 'Route is blocked by verified hazard or road closure';
      const ruleViolated = route.blockingCondition || route.ruleViolated || route.reasons?.[0]?.type || 'ROAD_CLOSED';
      rejectedRoutes.push({
        routeId: route.routeId,
        status: 'REJECTED',
        selectionStatus: 'REJECTED',
        distanceMeters: route.distanceMeters ?? null,
        durationSeconds: route.durationSeconds ?? null,
        encodedPolyline: route.encodedPolyline || null,
        score: route.score ?? null,
        blockingCondition: ruleViolated,
        evidenceSource: route.evidenceSource || route.reasons?.[0]?.source || 'ROAD_CONDITION_ENGINE',
        confidence: route.confidence || route.reasons?.[0]?.confidence || 'HIGH',
        freshness: route.freshness || route.reasons?.[0]?.freshness || 'N/A',
        rejectionReason: primaryRejection,
        ruleViolated,
        allReasons: route.reasons || []
      });
    } else if (route.status === 'VALID' || route.status === 'SELECTED' || route.status === 'FEASIBLE_ALTERNATIVE') {
      validRoutes.push(route);
    }
  }

  // Sort valid routes ascending by score (lowest score is best)
  validRoutes.sort((a, b) => (a.score ?? 0) - (b.score ?? 0));

  const decisionReasons = [];

  if (validRoutes.length === 0) {
    decisionReasons.push(
      scoredRoutes.length === 0
        ? 'No candidate routes returned by routing provider.'
        : `All ${scoredRoutes.length} candidate route(s) are blocked by active hazards or road closures.`
    );

    return {
      status: 'NO_SAFE_ROUTE_FOUND',
      primaryRoute: null,
      backupRoutes: [],
      rejectedRoutes,
      decisionReasons
    };
  }

  const primary = {
    ...validRoutes[0],
    selectionStatus: 'SELECTED',
    rejectionReason: null
  };

  const backups = validRoutes.slice(1).map((b, idx) => ({
    ...b,
    selectionStatus: 'FEASIBLE_ALTERNATIVE',
    rejectionReason: null,
    description: b.description || `Feasible alternative corridor (rank ${idx + 2}, score: ${b.score}).`
  }));

  decisionReasons.push(
    `Selected route ${primary.routeId} as PRIMARY with best risk-adjusted score of ${primary.score}.`
  );

  if (backups.length > 0) {
    const backupIds = backups.map(b => `${b.routeId} (score: ${b.score})`).join(', ');
    decisionReasons.push(`Designated ${backups.length} valid alternative(s) as FEASIBLE_ALTERNATIVE: ${backupIds}.`);
  } else {
    decisionReasons.push('No alternative valid routes available for backup designation.');
  }

  if (rejectedRoutes.length > 0) {
    decisionReasons.push(
      `Explicitly rejected ${rejectedRoutes.length} candidate route(s) due to verified safety or road closure rules.`
    );
  }

  return {
    status: 'ROUTE_FOUND',
    primaryRoute: primary,
    backupRoutes: backups,
    rejectedRoutes,
    decisionReasons
  };
}

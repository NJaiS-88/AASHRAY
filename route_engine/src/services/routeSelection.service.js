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
    if (route.status === 'INVALID') {
      const primaryRejection = route.reasons?.[0]?.message || 'Route is blocked by road closure/hazard';
      rejectedRoutes.push({
        routeId: route.routeId,
        status: 'INVALID',
        distanceMeters: route.distanceMeters,
        durationSeconds: route.durationSeconds,
        blockingCondition: route.blockingCondition || route.reasons?.[0]?.type || 'ROAD_BLOCKED',
        evidenceSource: route.reasons?.[0]?.source || 'OPENWEB_NINJA',
        confidence: route.reasons?.[0]?.confidence || 'HIGH',
        freshness: route.reasons?.[0]?.freshness || 'N/A',
        rejectionReason: primaryRejection,
        allReasons: route.reasons || []
      });
    } else if (route.status === 'VALID') {
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

  const primary = validRoutes[0];
  const backups = validRoutes.slice(1);

  decisionReasons.push(
    `Selected route ${primary.routeId} as PRIMARY with best risk-adjusted score of ${primary.score}.`
  );

  if (backups.length > 0) {
    const backupIds = backups.map(b => `${b.routeId} (score: ${b.score})`).join(', ');
    decisionReasons.push(`Designated ${backups.length} valid alternative(s) as BACKUP: ${backupIds}.`);
  } else {
    decisionReasons.push('No alternative valid routes available for backup designation.');
  }

  if (rejectedRoutes.length > 0) {
    decisionReasons.push(
      `Excluded ${rejectedRoutes.length} route(s) due to confirmed hazards/closures.`
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

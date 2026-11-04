/**
 * Default Route Scoring Configuration
 * Weights sum to 1.0:
 * - travelTimeWeight: 0.35 (Fastest route incentive)
 * - roadRiskWeight: 0.45 (Hazard avoidance based on severity & evidence confidence)
 * - uncertaintyWeight: 0.20 (Penalty for routes where condition data is UNKNOWN)
 */
export const DEFAULT_SCORING_CONFIG = {
  travelTimeWeight: 0.35,
  roadRiskWeight: 0.45,
  uncertaintyWeight: 0.20,
  maxScore: 100
};

/**
 * Normalizes travel times relatively across candidate routes.
 * 
 * The fastest candidate route gets 0.0 penalty.
 * The slowest route gets a normalized penalty up to 100.0 relative to excess time.
 * If all durations are equal or there is only 1 candidate, returns 0 for all.
 * 
 * Handles zero duration, missing duration, and 1 route without division by zero.
 * 
 * @param {Array<Object>} routes 
 * @returns {Map<string, number>} Map of routeId -> travelTimeScore (0 - 100)
 */
export function calculateTravelTimeScores(routes) {
  const scores = new Map();
  if (!Array.isArray(routes) || routes.length === 0) return scores;

  const validDurations = routes
    .map(r => (typeof r.durationSeconds === 'number' && !Number.isNaN(r.durationSeconds) ? Math.max(0, r.durationSeconds) : null))
    .filter(d => d !== null);

  if (validDurations.length === 0) {
    routes.forEach(r => scores.set(r.routeId, 0));
    return scores;
  }

  const minDuration = Math.min(...validDurations);
  const maxDuration = Math.max(...validDurations);
  const span = maxDuration - minDuration;

  routes.forEach(route => {
    const d = typeof route.durationSeconds === 'number' && !Number.isNaN(route.durationSeconds) ? Math.max(0, route.durationSeconds) : minDuration;
    // Base penalty scales with absolute travel time (e.g. 1 hour = 30 points, 10 mins = 5 points)
    const absoluteScore = Math.min(60, (d / 3600) * 30);
    if (span === 0) {
      scores.set(route.routeId, Number(absoluteScore.toFixed(2)));
    } else {
      // Combined: absolute duration baseline + relative penalty across competing options
      const relativePenalty = ((d - minDuration) / span) * 40;
      const combined = Math.min(100, absoluteScore + relativePenalty);
      scores.set(route.routeId, Number(combined.toFixed(2)));
    }
  });

  return scores;
}

/**
 * Computes road risk score and uncertainty score from the Road Condition Engine evaluation.
 * 
 * Status Mapping:
 * - BLOCKED:
 *   If high or very high confidence, route is INVALID.
 * - RISKY:
 *   Road risk score computed from severity and confidence of matched incidents.
 * - OPEN:
 *   0 road risk, 0 uncertainty.
 * - UNKNOWN:
 *   0.0 road risk, but receives an uncertainty score (e.g. 50.0 out of 100) reflecting limited data.
 * 
 * @param {Object} assessment - roadConditionAssessment { status, confidence, reasons }
 * @param {Array<Object>} matchedIncidents
 * @returns {{ isInvalid: boolean, roadRiskScore: number, uncertaintyScore: number, invalidReasons: Array<Object>, explanationReasons: Array<Object> }}
 */
export function calculateRiskAndUncertainty(assessment, matchedIncidents = [], route = null) {
  const status = assessment?.status || 'UNKNOWN';
  const reasons = assessment?.reasons || [];

  const invalidReasons = [];
  const explanationReasons = [];

  // Check for blocking conditions from assessment reasons
  for (const r of reasons) {
    const isClosure = r.type === 'ROAD_CLOSED' || r.type === 'ROAD_BLOCKED' || r.type === 'IMPASSABLE' || r.type === 'ROAD_IMPASSABLE' || status === 'BLOCKED';
    if (isClosure) {
      const conf = String(r.confidence || assessment.confidence || '').toUpperCase();
      // Fresh or high-confidence BLOCKED invalidates the route
      if (conf === 'HIGH' || conf === 'VERY_HIGH' || conf === 'MEDIUM') {
        invalidReasons.push({
          type: r.type || 'ROAD_CLOSED',
          message: r.message || `Candidate route is blocked: ${r.type} reported by ${r.source || 'provider'}`,
          source: r.source || 'OPENWEB_NINJA',
          evidenceId: r.evidenceId || null,
          confidence: r.confidence || assessment.confidence,
          freshness: r.ageSeconds !== undefined ? (r.ageSeconds <= 180 ? 'FRESH' : 'STALE') : 'UNKNOWN',
          dataAgeSeconds: r.ageSeconds ?? null
        });
      }
    }
  }

  // Also check directly for blocking incidents along matched corridor
  for (const inc of matchedIncidents) {
    const isBlocking = inc.isBlocking || inc.status === 'BLOCKED' || inc.conditionType === 'ROAD_CLOSED' || inc.type === 'ROAD_CLOSED' || inc.conditionType === 'IMPASSABLE' || inc.type === 'IMPASSABLE';
    if (isBlocking) {
      const alreadyAdded = invalidReasons.some(r => r.evidenceId && r.evidenceId === (inc.incidentId || inc.externalId));
      if (!alreadyAdded) {
        invalidReasons.push({
          type: inc.conditionType || inc.type || 'ROAD_CLOSED',
          message: `Candidate route intersects impassable road hazard: ${inc.conditionType || inc.type || 'ROAD_CLOSED'} (${inc.street || 'on corridor'}) reported by ${inc.source || 'provider'}`,
          source: inc.source || 'OPENWEB_NINJA',
          evidenceId: inc.incidentId || inc.externalId || null,
          confidence: inc.confidence || 'HIGH',
          freshness: inc.freshness || 'FRESH'
        });
      }
    }
  }

  if (invalidReasons.length > 0 || status === 'BLOCKED') {
    if (invalidReasons.length === 0) {
      invalidReasons.push({
        type: 'ROAD_BLOCKED',
        message: 'Route has been evaluated as BLOCKED by the road condition engine',
        source: 'ROAD_CONDITION_ENGINE',
        confidence: assessment.confidence || 'HIGH',
        freshness: 'FRESH'
      });
    }
    return {
      isInvalid: true,
      roadRiskScore: 100,
      uncertaintyScore: 0,
      invalidReasons,
      explanationReasons: invalidReasons
    };
  }

  // Not blocked, calculate road risk
  let roadRiskScore = 0;
  let uncertaintyScore = 0;

  if (status === 'UNKNOWN' || (!matchedIncidents.length && reasons.length === 0)) {
    // Uncertainty scales with route corridor extent (base 15 + ~0.8/km)
    const distKm = (route?.distanceMeters ? route.distanceMeters / 1000 : route?.distanceKm) || 5;
    uncertaintyScore = Math.min(60, 15 + Math.round(distKm * 0.8));
    explanationReasons.push({
      type: 'LIMITED_EVIDENCE',
      message: `No real-time road condition incidents detected along corridor (${distKm.toFixed(1)} km). Route uncertainty calibrated to corridor length.`,
      source: 'ROAD_CONDITION_ENGINE',
      confidence: 'UNKNOWN',
      freshness: 'N/A'
    });
  } else if (status === 'RISKY') {
    // Compute severity & confidence weighted risk
    let maxIncidentRisk = 0;
    for (const inc of matchedIncidents) {
      let baseSeverity = 25; // default moderate
      const condType = inc.conditionType || inc.type;
      if (condType === 'ACCIDENT') baseSeverity = 50;
      if (condType === 'TRAFFIC' || condType === 'JAM') baseSeverity = 35;
      if (condType === 'FLOODED') baseSeverity = 70;

      const confMultiplier = inc.confidence === 'VERY_HIGH' ? 1.0 :
                             inc.confidence === 'HIGH' ? 0.9 :
                             inc.confidence === 'MEDIUM' ? 0.7 : 0.5;

      const incidentScore = Math.min(100, baseSeverity * confMultiplier);
      if (incidentScore > maxIncidentRisk) {
        maxIncidentRisk = incidentScore;
      }

      explanationReasons.push({
        type: condType,
        message: `Affected by ${condType} (${inc.street || 'on route'}) at distance ${inc.distanceFromRouteMeters || 0}m`,
        source: inc.source || 'OPENWEB_NINJA',
        evidenceId: inc.incidentId || inc.externalId || null,
        confidence: inc.confidence || 'MEDIUM',
        freshness: inc.freshness || 'N/A'
      });
    }

    roadRiskScore = Math.min(100, Math.max(20, maxIncidentRisk));
  } else if (status === 'OPEN') {
    roadRiskScore = 0;
    uncertaintyScore = 0;
    explanationReasons.push({
      type: 'VERIFIED_OPEN',
      message: 'Road confirmed open by official monitoring sources.',
      source: 'ROAD_CONDITION_ENGINE',
      confidence: assessment.confidence || 'HIGH'
    });
  }

  return {
    isInvalid: false,
    roadRiskScore: Number(roadRiskScore.toFixed(2)),
    uncertaintyScore: Number(uncertaintyScore.toFixed(2)),
    invalidReasons: [],
    explanationReasons
  };
}

/**
 * Scores candidate routes deterministically based on travel time, road condition risk,
 * uncertainty, and resource policy weights.
 * 
 * @param {Object} params
 * @param {Array<Object>} params.candidateRoutes - Candidate routes with roadConditionAssessment and matchedIncidents
 * @param {Object} [params.policy] - Resource policy containing weights { travelTimeWeight, roadRiskWeight, uncertaintyWeight }
 * @returns {Array<Object>} Evaluated routes with status (VALID | INVALID), deterministic score, breakdown, and reasons
 */
export function scoreCandidateRoutes({ candidateRoutes = [], policy = null }) {
  if (!Array.isArray(candidateRoutes) || candidateRoutes.length === 0) {
    return [];
  }

  const weights = policy?.weights || {
    travelTimeWeight: DEFAULT_SCORING_CONFIG.travelTimeWeight,
    roadRiskWeight: DEFAULT_SCORING_CONFIG.roadRiskWeight,
    uncertaintyWeight: DEFAULT_SCORING_CONFIG.uncertaintyWeight
  };

  // 1. Calculate relative travel time scores
  const travelTimeScores = calculateTravelTimeScores(candidateRoutes);

  // 2. Score each route individually
  return candidateRoutes.map(route => {
    const routeId = route.routeId;

    // Check for missing geometry / unavailable candidate
    if (!route.encodedPolyline && (!route.coordinates || route.coordinates.length < 2)) {
      return {
        ...route,
        status: 'UNAVAILABLE',
        score: null,
        reasons: [{
          type: 'MISSING_GEOMETRY',
          message: 'Route candidate missing geometry from routing provider.',
          source: 'ROUTING_PROVIDER',
          confidence: 'HIGH'
        }]
      };
    }

    const ttScore = travelTimeScores.get(routeId) ?? 0;
    const assessment = route.roadConditionAssessment || { status: 'UNKNOWN', confidence: 'UNKNOWN', reasons: [] };
    const matchedIncidents = route.matchedIncidents || [];

    const { isInvalid, roadRiskScore, uncertaintyScore, invalidReasons, explanationReasons } = 
      calculateRiskAndUncertainty(assessment, matchedIncidents, route);

    if (isInvalid) {
      return {
        ...route,
        status: 'INVALID',
        score: null,
        breakdown: {
          travelTimeScore: ttScore,
          roadRiskScore: 100,
          uncertaintyScore: 0
        },
        reasons: invalidReasons
      };
    }

    // Check if route risk violates configured maximum allowed threshold
    const maxAllowedRisk = weights.maxRoadRiskThreshold ?? (policy?.maxRoadRiskThreshold ?? 95);
    if (roadRiskScore >= maxAllowedRisk) {
      return {
        ...route,
        status: 'INVALID',
        score: null,
        breakdown: {
          travelTimeScore: ttScore,
          roadRiskScore,
          uncertaintyScore
        },
        reasons: [{
          type: 'MAX_RISK_THRESHOLD_EXCEEDED',
          message: `Candidate route risk score (${roadRiskScore}) exceeds maximum allowed risk threshold (${maxAllowedRisk}) for ${policy?.resourceType || 'vehicle'}.`,
          source: 'RESOURCE_RISK_POLICY',
          confidence: 'HIGH'
        }]
      };
    }

    // Weighted composite score
    // finalScore = (w_tt * ttScore) + (w_risk * riskScore) + (w_unc * uncScore)
    const weightedTT = Number((weights.travelTimeWeight * ttScore).toFixed(2));
    const weightedRisk = Number((weights.roadRiskWeight * roadRiskScore).toFixed(2));
    const weightedUnc = Number((weights.uncertaintyWeight * uncertaintyScore).toFixed(2));
    const finalScore = Number((weightedTT + weightedRisk + weightedUnc).toFixed(2));

    return {
      ...route,
      status: 'VALID',
      score: finalScore,
      breakdown: {
        travelTimeScore: weightedTT,
        roadRiskScore: weightedRisk,
        uncertaintyScore: weightedUnc
      },
      reasons: explanationReasons
    };
  });
}

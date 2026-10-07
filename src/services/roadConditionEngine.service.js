/**
 * Road Condition Engine
 * 
 * Aggregates road-condition evidence from multiple sources:
 * - OPENWEB_NINJA
 * - CITIZEN
 * - RESPONDER
 * - GOVERNMENT
 * - WEATHER
 * - SATELLITE
 * 
 * Rules:
 * 1. No evidence does NOT mean OPEN. No evidence means UNKNOWN.
 * 2. A fresh, high-confidence ROAD_CLOSED observation produces BLOCKED.
 * 3. A responder-confirmed impassable road produces BLOCKED.
 * 4. A citizen flooding report initially produces RISKY/UNKNOWN depending on evidence and confidence, not automatically BLOCKED.
 * 5. Weather influences risk but must NOT automatically mark a road BLOCKED.
 * 6. A general government flood warning must NOT automatically close every road.
 * 7. An explicit official road closure can produce BLOCKED.
 * 8. Evidence must remain traceable.
 * 9. Never add flood depth.
 */

/**
 * Calculates evidence age in seconds from reportedAt or updatedAt.
 */
function getAgeSeconds(reportedAt) {
  if (!reportedAt) return null;
  const time = new Date(reportedAt).getTime();
  if (Number.isNaN(time)) return null;
  return Math.max(0, Math.round((Date.now() - time) / 1000));
}

/**
 * Normalizes confidence level string to standard rating.
 */
function normalizeConfidence(confidence) {
  if (!confidence) return 'UNKNOWN';
  const upper = String(confidence).toUpperCase();
  if (upper === 'VERY_HIGH' || upper === 'HIGH') return upper;
  if (upper === 'MEDIUM') return 'MEDIUM';
  if (upper === 'LOW') return 'LOW';
  return 'UNKNOWN';
}

/**
 * Evaluates an array of evidence items affecting a segment or route.
 * 
 * @param {Array<Object>} evidenceList - List of evidence records
 * @returns {{ status: 'OPEN'|'RISKY'|'BLOCKED'|'UNKNOWN', confidence: 'LOW'|'MEDIUM'|'HIGH'|'VERY_HIGH'|'UNKNOWN', reasons: Array<Object>, evidence: Array<Object> }}
 */
export function evaluateRoadConditions(evidenceList = []) {
  if (!Array.isArray(evidenceList) || evidenceList.length === 0) {
    return {
      status: 'UNKNOWN',
      confidence: 'UNKNOWN',
      reasons: [],
      evidence: []
    };
  }

  const reasons = [];
  let isBlocked = false;
  let isRisky = false;
  let hasResponderBlocked = false;
  let hasOpenWebClosed = false;
  let hasOfficialClosure = false;
  let highestConfidence = 'LOW';

  const confidenceRank = {
    'UNKNOWN': 0,
    'LOW': 1,
    'MEDIUM': 2,
    'HIGH': 3,
    'VERY_HIGH': 4
  };

  const updateHighestConfidence = (conf) => {
    if (confidenceRank[conf] > confidenceRank[highestConfidence]) {
      highestConfidence = conf;
    }
  };

  for (const item of evidenceList) {
    const source = item.source || item.rawMetadata?.source || 'UNKNOWN';
    const conditionType = item.conditionType || item.type || item.rawMetadata?.conditionType || 'OTHER';
    const blockAlertType = item.blockAlertType || item.rawMetadata?.blockAlertType;
    const reportedAt = item.reportedAt || item.updatedAt || item.rawMetadata?.updateTime;
    const ageSec = getAgeSeconds(reportedAt);
    const itemConf = normalizeConfidence(item.confidence || item.rawMetadata?.confidence);

    const isFresh = ageSec === null || ageSec <= 1800; // 30 minutes threshold for freshness

    // OpenWeb Ninja rule
    if (source === 'OPENWEB_NINJA') {
      if (blockAlertType === 'ROAD_CLOSED' || conditionType === 'ROAD_CLOSED') {
        const conf = isFresh ? 'VERY_HIGH' : 'HIGH';
        hasOpenWebClosed = true;
        isBlocked = true;
        updateHighestConfidence(conf);
        reasons.push({
          source: 'OPENWEB_NINJA',
          type: 'ROAD_CLOSED',
          confidence: conf,
          ageSeconds: ageSec
        });
        continue;
      }

      if (conditionType === 'ACCIDENT' || conditionType === 'TRAFFIC' || conditionType === 'JAM') {
        isRisky = true;
        updateHighestConfidence('MEDIUM');
        reasons.push({
          source: 'OPENWEB_NINJA',
          type: conditionType,
          confidence: itemConf || 'MEDIUM',
          ageSeconds: ageSec
        });
        continue;
      }
    }

    // Responder rule
    if (source === 'RESPONDER') {
      const vehiclePassable = item.rawMetadata?.vehiclePassable ?? (item.vehiclePassable ?? null);
      if (conditionType === 'ROAD_BLOCKED' || conditionType === 'ROAD_CLOSED' || vehiclePassable === false) {
        hasResponderBlocked = true;
        isBlocked = true;
        updateHighestConfidence('VERY_HIGH');
        reasons.push({
          source: 'RESPONDER',
          type: conditionType,
          confidence: 'VERY_HIGH',
          ageSeconds: ageSec
        });
        continue;
      }

      isRisky = true;
      updateHighestConfidence('HIGH');
      reasons.push({
        source: 'RESPONDER',
        type: conditionType,
        confidence: 'HIGH',
        ageSeconds: ageSec
      });
      continue;
    }

    // Government rule
    if (source === 'GOVERNMENT') {
      if (conditionType === 'ROAD_CLOSED' || conditionType === 'ROAD_BLOCKED') {
        hasOfficialClosure = true;
        isBlocked = true;
        updateHighestConfidence('VERY_HIGH');
        reasons.push({
          source: 'GOVERNMENT',
          type: 'ROAD_CLOSED',
          confidence: 'VERY_HIGH',
          ageSeconds: ageSec
        });
        continue;
      }

      // General warning does not close roads
      isRisky = true;
      updateHighestConfidence('MEDIUM');
      reasons.push({
        source: 'GOVERNMENT',
        type: conditionType,
        confidence: 'MEDIUM',
        ageSeconds: ageSec
      });
      continue;
    }

    // Citizen rule: low initial confidence, produces RISKY or UNKNOWN, NOT automatically BLOCKED
    if (source === 'CITIZEN') {
      const citizenConf = itemConf === 'UNKNOWN' ? 'LOW' : itemConf;
      isRisky = true;
      updateHighestConfidence(citizenConf);
      reasons.push({
        source: 'CITIZEN',
        type: conditionType,
        confidence: citizenConf,
        ageSeconds: ageSec
      });
      continue;
    }

    // Weather rule: influences risk, must NOT mark BLOCKED
    if (source === 'WEATHER') {
      isRisky = true;
      updateHighestConfidence('MEDIUM');
      reasons.push({
        source: 'WEATHER',
        type: conditionType,
        confidence: 'MEDIUM',
        ageSeconds: ageSec
      });
      continue;
    }

    // Satellite rule
    if (source === 'SATELLITE') {
      isRisky = true;
      updateHighestConfidence('MEDIUM');
      reasons.push({
        source: 'SATELLITE',
        type: conditionType,
        confidence: 'MEDIUM',
        ageSeconds: ageSec
      });
      continue;
    }

    // Fallback for generic or unknown sources
    if (conditionType === 'ROAD_CLOSED' || conditionType === 'ROAD_BLOCKED') {
      isBlocked = true;
      updateHighestConfidence('MEDIUM');
      reasons.push({
        source,
        type: conditionType,
        confidence: 'MEDIUM',
        ageSeconds: ageSec
      });
    } else {
      isRisky = true;
      updateHighestConfidence('LOW');
      reasons.push({
        source,
        type: conditionType,
        confidence: 'LOW',
        ageSeconds: ageSec
      });
    }
  }

  // Determine final status
  let finalStatus = 'UNKNOWN';
  if (isBlocked || hasResponderBlocked || hasOpenWebClosed || hasOfficialClosure) {
    finalStatus = 'BLOCKED';
  } else if (isRisky) {
    finalStatus = 'RISKY';
  }

  return {
    status: finalStatus,
    confidence: highestConfidence,
    reasons,
    evidence: evidenceList
  };
}

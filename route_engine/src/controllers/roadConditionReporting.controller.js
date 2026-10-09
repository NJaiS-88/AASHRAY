import prisma from '../config/prisma.js';

/**
 * Controller for manual road-condition reporting APIs
 */

/**
 * Maps condition string to Prisma ConditionType enum
 */
function normalizeConditionType(type) {
  const upper = String(type || '').toUpperCase();
  if (upper === 'FLOODED') return 'FLOODED';
  if (upper === 'ROAD_BLOCKED') return 'ROAD_BLOCKED';
  if (upper === 'ROAD_CLOSED') return 'ROAD_CLOSED';
  if (upper === 'ACCIDENT') return 'ACCIDENT';
  if (upper === 'TRAFFIC') return 'TRAFFIC';
  return 'OTHER';
}

/**
 * Maps severity string to numeric level
 */
function normalizeSeverity(severity) {
  if (typeof severity === 'number') return severity;
  const upper = String(severity || '').toUpperCase();
  if (upper === 'CRITICAL') return 5;
  if (upper === 'HIGH') return 4;
  if (upper === 'MEDIUM') return 3;
  if (upper === 'LOW') return 2;
  return 1;
}

/**
 * POST /api/reports/citizen
 * 
 * Supports:
 * {
 *   "latitude": ...,
 *   "longitude": ...,
 *   "conditionType": "FLOODED",
 *   "severity": "HIGH",
 *   "description": "..."
 * }
 */
export async function submitCitizenReport(req, res, next) {
  try {
    const { latitude, longitude, conditionType, severity, description } = req.body;

    // Validate coordinates
    if (typeof latitude !== 'number' || typeof longitude !== 'number') {
      return res.status(400).json({
        success: false,
        message: 'latitude and longitude are required numbers'
      });
    }

    const condType = normalizeConditionType(conditionType);
    const numericSeverity = normalizeSeverity(severity);

    // Initial status for citizen report: RISKY or UNKNOWN, never automatically BLOCKED
    const status = 'RISKY';
    const confidence = 'LOW'; // Citizen reports have lower initial confidence

    const rawMetadata = {
      reporterId: req.user?.id || 'anonymous',
      reporterRole: 'CITIZEN',
      conditionType: condType,
      severityString: severity,
      description: description || null,
      coordinates: { latitude, longitude }
    };

    const evidence = await prisma.roadConditionEvidence.create({
      data: {
        source: 'CITIZEN',
        externalId: `citizen-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
        conditionType: condType,
        status,
        latitude,
        longitude,
        severity: numericSeverity,
        confidence,
        reportedAt: new Date(),
        rawMetadata
      }
    });

    res.status(201).json({
      success: true,
      message: 'Citizen report recorded successfully as road-condition evidence',
      data: {
        evidenceId: evidence.id,
        source: evidence.source,
        conditionType: evidence.conditionType,
        status: evidence.status,
        confidence: evidence.confidence,
        latitude: evidence.latitude,
        longitude: evidence.longitude,
        reportedAt: evidence.reportedAt
      }
    });
  } catch (err) {
    next(err);
  }
}

/**
 * POST /api/reports/responder
 * 
 * Supports:
 * {
 *   "latitude": ...,
 *   "longitude": ...,
 *   "conditionType": "ROAD_BLOCKED",
 *   "severity": "CRITICAL",
 *   "vehiclePassable": false,
 *   "description": "..."
 * }
 */
export async function submitResponderReport(req, res, next) {
  try {
    const { latitude, longitude, conditionType, severity, vehiclePassable, description } = req.body;

    if (typeof latitude !== 'number' || typeof longitude !== 'number') {
      return res.status(400).json({
        success: false,
        message: 'latitude and longitude are required numbers'
      });
    }

    const condType = normalizeConditionType(conditionType);
    const numericSeverity = normalizeSeverity(severity);

    // Responder rule: impassable road or ROAD_BLOCKED produces BLOCKED with higher confidence
    const isImpassable = vehiclePassable === false || condType === 'ROAD_BLOCKED' || condType === 'ROAD_CLOSED';
    const status = isImpassable ? 'BLOCKED' : 'RISKY';
    const confidence = 'HIGH'; // Responder reports have higher confidence

    const rawMetadata = {
      reporterId: req.user?.id || 'responder-user',
      reporterRole: 'RESPONDER',
      conditionType: condType,
      severityString: severity,
      vehiclePassable: vehiclePassable ?? null,
      description: description || null,
      coordinates: { latitude, longitude }
    };

    const evidence = await prisma.roadConditionEvidence.create({
      data: {
        source: 'RESPONDER',
        externalId: `responder-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
        conditionType: condType,
        status,
        latitude,
        longitude,
        severity: numericSeverity,
        confidence,
        reportedAt: new Date(),
        rawMetadata
      }
    });

    res.status(201).json({
      success: true,
      message: 'Responder report recorded successfully as high-confidence evidence',
      data: {
        evidenceId: evidence.id,
        source: evidence.source,
        conditionType: evidence.conditionType,
        status: evidence.status,
        confidence: evidence.confidence,
        vehiclePassable: vehiclePassable ?? null,
        latitude: evidence.latitude,
        longitude: evidence.longitude,
        reportedAt: evidence.reportedAt
      }
    });
  } catch (err) {
    next(err);
  }
}

import prisma from '../config/prisma.js';

/**
 * Maps OpenWeb/Waze incident condition to database ConditionType and RoadStatus.
 *
 * Rules:
 * - If blockAlertType === 'ROAD_CLOSED' or type === 'ROAD_CLOSED':
 *     conditionType = 'ROAD_CLOSED', status = 'BLOCKED'
 * - If type === 'ACCIDENT':
 *     conditionType = 'ACCIDENT', status = 'RISKY'
 * - If type === 'JAM':
 *     conditionType = 'TRAFFIC', status = 'RISKY'
 * - Never claim flood unless another source explicitly reports flooding.
 * - Absence of an incident does NOT mean safe.
 */
export function mapIncidentToEvidence(incident) {
  const isClosed = incident.blockAlertType === 'ROAD_CLOSED' || incident.type === 'ROAD_CLOSED';

  let conditionType = 'OTHER';
  let status = 'UNKNOWN';

  if (isClosed) {
    conditionType = 'ROAD_CLOSED';
    status = 'BLOCKED';
  } else if (incident.type === 'ACCIDENT') {
    conditionType = 'ACCIDENT';
    status = 'RISKY';
  } else if (incident.type === 'JAM') {
    conditionType = 'TRAFFIC';
    status = 'RISKY';
  }

  // Parse reportedAt date safely
  const reportedAt = incident.updatedAt ? new Date(incident.updatedAt) : new Date();

  // If road is closed, confidence is HIGH
  let confidence = incident.confidence || 'UNKNOWN';
  if (isClosed && confidence !== 'HIGH') {
    confidence = 'HIGH';
  }

  // Normalize coordinates
  const latitude = typeof incident.latitude === 'number' ? incident.latitude : 0;
  const longitude = typeof incident.longitude === 'number' ? incident.longitude : 0;

  // Build raw metadata preserving all fields
  const rawMetadata = {
    provider: incident.provider || 'WAZE',
    externalId: incident.externalId || null,
    conditionType: incident.type,
    coordinates: {
      latitude: incident.latitude,
      longitude: incident.longitude
    },
    lineCoordinates: incident.lineCoordinates || [],
    street: incident.street || null,
    city: incident.city || null,
    severity: incident.severityLevel ?? null,
    speed: incident.speedKmh ?? null,
    length: incident.lengthMeters ?? null,
    blockAlertType: incident.blockAlertType || null,
    blockAlertId: incident.blockAlertId || null,
    updateTime: incident.updatedAt || null,
    freshness: incident.freshness || null,
    dataAgeSeconds: incident.dataAgeSeconds ?? null,
    confidence
  };

  return {
    source: 'OPENWEB_NINJA',
    externalId: incident.externalId ? String(incident.externalId) : null,
    conditionType,
    status,
    latitude,
    longitude,
    street: incident.street || null,
    severity: typeof incident.severityLevel === 'number' ? incident.severityLevel : (incident.severityLevel ? parseInt(incident.severityLevel, 10) : null),
    confidence,
    reportedAt,
    expiresAt: null,
    rawMetadata
  };
}

/**
 * Stores or updates road-condition evidence from OpenWeb incidents in the database.
 * Uses upsert on [source, externalId] where possible, or finds existing record.
 * 
 * @param {Array<Object>} incidents - Normalized incidents from OpenWeb Ninja service
 * @returns {Promise<Array<Object>>} Stored evidence records
 */
export async function storeRoadConditionEvidences(incidents) {
  if (!Array.isArray(incidents) || incidents.length === 0) {
    return [];
  }

  const storedRecords = [];

  for (const incident of incidents) {
    if (!incident.externalId && (incident.latitude === null || incident.longitude === null)) {
      continue;
    }

    const evidenceData = mapIncidentToEvidence(incident);

    try {
      let existingRecord = null;
      if (evidenceData.externalId) {
        existingRecord = await prisma.roadConditionEvidence.findFirst({
          where: {
            source: evidenceData.source,
            externalId: evidenceData.externalId
          }
        });
      }

      if (existingRecord) {
        const updated = await prisma.roadConditionEvidence.update({
          where: { id: existingRecord.id },
          data: {
            conditionType: evidenceData.conditionType,
            status: evidenceData.status,
            latitude: evidenceData.latitude,
            longitude: evidenceData.longitude,
            street: evidenceData.street,
            severity: evidenceData.severity,
            confidence: evidenceData.confidence,
            reportedAt: evidenceData.reportedAt,
            rawMetadata: evidenceData.rawMetadata
          }
        });
        storedRecords.push(updated);
      } else {
        const created = await prisma.roadConditionEvidence.create({
          data: evidenceData
        });
        storedRecords.push(created);
      }
    } catch (err) {
      console.error(`Error saving road condition evidence for externalId ${incident.externalId}:`, err.message);
    }
  }

  return storedRecords;
}

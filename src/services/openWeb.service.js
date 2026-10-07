import axios from 'axios';
import { config } from '../config/env.js';

const API_URL = 'https://api.openwebninja.com/waze/alerts-and-jams';

function ageSeconds(timestamp) {
  if (!timestamp) return null;
  const time = new Date(timestamp).getTime();
  if (Number.isNaN(time)) return null;
  return Math.round((Date.now() - time) / 1000);
}

function calculateConfidence(jam, age) {
  let score = 0;
  if (jam.block_alert_type === 'ROAD_CLOSED') score += 50;
  if (jam.speed_kmh === 0) score += 20;
  if (Number(jam.level) >= 4) score += 20;
  if (jam.block_alert_id) score += 10;
  if (age !== null && age <= 180) score += 10;
  
  if (score >= 80) return 'HIGH';
  if (score >= 50) return 'MEDIUM';
  return 'LOW';
}

/**
 * Validates bounding box coordinates
 */
function validateBoundingBox(bottomLeft, topRight) {
  if (!bottomLeft || typeof bottomLeft !== 'string') throw new Error('bottomLeft must be a string formatted as "lat,lon"');
  if (!topRight || typeof topRight !== 'string') throw new Error('topRight must be a string formatted as "lat,lon"');
  
  const blParts = bottomLeft.split(',');
  const trParts = topRight.split(',');
  
  if (blParts.length !== 2 || trParts.length !== 2) {
    throw new Error('Bounding box coordinates must be "lat,lon"');
  }
}

/**
 * Fetches Waze alerts and jams from OpenWeb Ninja and returns normalized incidents.
 * @param {Object} params
 * @param {string} params.bottomLeft - "lat,lon"
 * @param {string} params.topRight - "lat,lon"
 */
export async function getRoadIncidents({ bottomLeft, topRight }) {
  validateBoundingBox(bottomLeft, topRight);

  const apiKey = config.openWebNinjaApiKey;
  if (!apiKey || apiKey === 'dummy_key') {
    throw new Error('OPENWEBNINJA_API_KEY is not configured with a valid key');
  }

  const params = {
    bottom_left: bottomLeft,
    top_right: topRight
  };

  const response = await axios.get(API_URL, {
    params,
    headers: {
      'X-API-Key': apiKey,
      'Accept': 'application/json'
    },
    timeout: 30000
  });

  const data = response.data || {};
  const rawJams = data.jams || [];
  const rawAlerts = data.alerts || [];

  const incidents = [];

  // Process Jams
  for (const jam of rawJams) {
    const age = ageSeconds(jam.update_datetime_utc);
    const freshness = (age !== null && age <= 180) ? 'FRESH' : 'STALE';
    const confidence = calculateConfidence(jam, age);

    let type = 'JAM';
    if (jam.block_alert_type === 'ROAD_CLOSED') {
      type = 'ROAD_CLOSED';
    }

    let latitude = null;
    let longitude = null;
    if (Array.isArray(jam.line_coordinates) && jam.line_coordinates.length > 0) {
      latitude = jam.line_coordinates[0].lat;
      longitude = jam.line_coordinates[0].lon;
    }

    incidents.push({
      source: 'OPENWEB_NINJA',
      provider: 'WAZE',
      externalId: jam.jam_id,
      type,
      street: jam.street,
      city: jam.city,
      latitude,
      longitude,
      lineCoordinates: jam.line_coordinates || [],
      speedKmh: jam.speed_kmh,
      severityLevel: jam.level,
      lengthMeters: jam.length_meters,
      blockAlertType: jam.block_alert_type,
      blockAlertId: jam.block_alert_id,
      updatedAt: jam.update_datetime_utc,
      dataAgeSeconds: age,
      freshness,
      confidence
    });
  }

  // Process Alerts (optional, since the test code also iterated alerts)
  for (const alert of rawAlerts) {
    const age = ageSeconds(alert.update_datetime_utc);
    const freshness = (age !== null && age <= 180) ? 'FRESH' : 'STALE';

    incidents.push({
      source: 'OPENWEB_NINJA',
      provider: 'WAZE',
      externalId: alert.alert_id,
      type: alert.type || 'ALERT',
      street: alert.street,
      city: alert.city,
      latitude: alert.location?.y || null,
      longitude: alert.location?.x || null,
      lineCoordinates: alert.location ? [{ lat: alert.location.y, lon: alert.location.x }] : [],
      speedKmh: null,
      severityLevel: null,
      lengthMeters: null,
      blockAlertType: null,
      blockAlertId: null,
      updatedAt: alert.update_datetime_utc,
      dataAgeSeconds: age,
      freshness,
      confidence: 'UNKNOWN' 
    });
  }

  return incidents;
}

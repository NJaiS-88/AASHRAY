/**
 * Utility to calculate bounding box [minLat, minLng, maxLat, maxLng]
 * for a route or pair of coordinates with an optional safety buffer/padding.
 */

/**
 * Calculates a bounding box covering origin, destination, and optionally intermediate route points.
 * 
 * @param {Object} options
 * @param {Object} options.origin - { latitude, longitude }
 * @param {Object} options.destination - { latitude, longitude }
 * @param {Array<[number, number]>} [options.points] - Optional array of [latitude, longitude] pairs (e.g. from polyline)
 * @param {number} [options.paddingDegrees=0.03] - Padding in degrees (approx 3.3km buffer at equator)
 * @returns {{ bottomLeft: string, topRight: string, minLat: number, minLng: number, maxLat: number, maxLng: number }}
 */
export function calculateBoundingBox({ origin, destination, points = [], paddingDegrees = 0.03 }) {
  let minLat = Math.min(origin.latitude, destination.latitude);
  let maxLat = Math.max(origin.latitude, destination.latitude);
  let minLng = Math.min(origin.longitude, destination.longitude);
  let maxLng = Math.max(origin.longitude, destination.longitude);

  if (Array.isArray(points) && points.length > 0) {
    for (const pt of points) {
      const lat = pt[0];
      const lng = pt[1];
      if (lat < minLat) minLat = lat;
      if (lat > maxLat) maxLat = lat;
      if (lng < minLng) minLng = lng;
      if (lng > maxLng) maxLng = lng;
    }
  }

  // Apply padding
  minLat = Number((minLat - paddingDegrees).toFixed(6));
  maxLat = Number((maxLat + paddingDegrees).toFixed(6));
  minLng = Number((minLng - paddingDegrees).toFixed(6));
  maxLng = Number((maxLng + paddingDegrees).toFixed(6));

  return {
    bottomLeft: `${minLat},${minLng}`,
    topRight: `${maxLat},${maxLng}`,
    minLat,
    minLng,
    maxLat,
    maxLng
  };
}

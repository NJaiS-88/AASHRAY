/**
 * Resource and Vehicle Risk Policies
 * 
 * Defines routing risk tolerance and scoring weight configurations
 * according to application-level resource types and mission priorities.
 * 
 * IMPORTANT:
 * These are routing policies, NOT physical vehicle capability claims.
 * We do not define maximum flood depth, clearance, or vehicle weight.
 * 
 * Supported resource types:
 * - AMBULANCE: High emphasis on travel-time speed but extremely intolerant of blocked/high-risk obstacles.
 * - RELIEF_TRUCK: Balances travel time and road stability/safety for heavy transport.
 * - RESCUE_VEHICLE: Designed for hazard response, safety-conscious and capable of navigating moderate delays.
 * - DEFAULT: Balanced conservative baseline for unspecified or generic resources.
 */

export const RESOURCE_POLICIES = {
  AMBULANCE: {
    resourceType: 'AMBULANCE',
    description: 'Emergency medical vehicle: high speed importance with strict hazard avoidance',
    travelTimeWeight: 0.40,
    roadRiskWeight: 0.50,
    uncertaintyWeight: 0.10,
    blockingConfidenceThreshold: 'HIGH', // High or Very High blocks the route
    allowedBlocked: false
  },
  RELIEF_TRUCK: {
    resourceType: 'RELIEF_TRUCK',
    description: 'Heavy logistics/cargo: balances travel time and road surface risk',
    travelTimeWeight: 0.35,
    roadRiskWeight: 0.45,
    uncertaintyWeight: 0.20,
    blockingConfidenceThreshold: 'HIGH',
    allowedBlocked: false
  },
  RESCUE_VEHICLE: {
    resourceType: 'RESCUE_VEHICLE',
    description: 'Disaster response unit: prioritized for safe mission access and robust routing',
    travelTimeWeight: 0.30,
    roadRiskWeight: 0.55,
    uncertaintyWeight: 0.15,
    blockingConfidenceThreshold: 'HIGH',
    allowedBlocked: false
  },
  DEFAULT: {
    resourceType: 'DEFAULT',
    description: 'Standard conservative routing policy',
    travelTimeWeight: 0.35,
    roadRiskWeight: 0.45,
    uncertaintyWeight: 0.20,
    blockingConfidenceThreshold: 'HIGH',
    allowedBlocked: false
  }
};

/**
 * Priority multipliers and adjustments
 * If priority is CRITICAL, risk sensitivity increases.
 * Note: A confirmed blocked road remains blocked under all priorities.
 */
export const PRIORITY_CONFIG = {
  LOW: {
    riskMultiplier: 0.9,
    uncertaintyMultiplier: 0.9
  },
  MEDIUM: {
    riskMultiplier: 1.0,
    uncertaintyMultiplier: 1.0
  },
  HIGH: {
    riskMultiplier: 1.15,
    uncertaintyMultiplier: 1.1
  },
  CRITICAL: {
    riskMultiplier: 1.3,
    uncertaintyMultiplier: 1.2
  }
};

/**
 * Retrieves the resource routing policy for a given resource type and priority.
 * 
 * @param {Object} options
 * @param {string} [options.resourceType] - AMBULANCE, RELIEF_TRUCK, RESCUE_VEHICLE, etc.
 * @param {string} [options.priority='MEDIUM'] - LOW, MEDIUM, HIGH, CRITICAL
 * @returns {Object} Effective routing policy configuration with weights summing to 1.0
 */
export function getResourcePolicy({ resourceType, priority = 'MEDIUM' } = {}) {
  const normType = (resourceType || '').toUpperCase();
  const basePolicy = RESOURCE_POLICIES[normType] || RESOURCE_POLICIES.DEFAULT;

  const normPriority = (priority || 'MEDIUM').toUpperCase();
  const priorityMod = PRIORITY_CONFIG[normPriority] || PRIORITY_CONFIG.MEDIUM;

  // Clone base policy weights
  let { travelTimeWeight, roadRiskWeight, uncertaintyWeight } = basePolicy;

  // When priority is CRITICAL or HIGH, adjust roadRisk and uncertainty sensitivity slightly
  roadRiskWeight *= priorityMod.riskMultiplier;
  uncertaintyWeight *= priorityMod.uncertaintyMultiplier;

  // Re-normalize weights so their sum strictly equals 1.0
  const sum = travelTimeWeight + roadRiskWeight + uncertaintyWeight;
  travelTimeWeight = Number((travelTimeWeight / sum).toFixed(4));
  roadRiskWeight = Number((roadRiskWeight / sum).toFixed(4));
  uncertaintyWeight = Number((1.0 - (travelTimeWeight + roadRiskWeight)).toFixed(4));

  return {
    resourceType: basePolicy.resourceType,
    isFallback: !RESOURCE_POLICIES[normType],
    priority: normPriority,
    weights: {
      travelTimeWeight,
      roadRiskWeight,
      uncertaintyWeight
    },
    blockingConfidenceThreshold: basePolicy.blockingConfidenceThreshold,
    allowedBlocked: false
  };
}

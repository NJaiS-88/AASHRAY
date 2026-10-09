import { z } from 'zod';
import { optimizeRoutePipeline } from '../services/routeOptimization.service.js';
import { evaluateAndReroute } from '../services/rerouting.service.js';
import { getMissionRouteState } from '../services/missionTracking.service.js';

const optimizeRouteSchema = z.object({
  source: z.object({
    latitude: z.number().min(-90).max(90),
    longitude: z.number().min(-180).max(180)
  }),
  destination: z.object({
    latitude: z.number().min(-90).max(90),
    longitude: z.number().min(-180).max(180)
  }),
  resourceId: z.string().optional(),
  resourceType: z.string().optional(),
  priority: z.enum(['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']).optional(),
  missionId: z.string().optional(),
  options: z.object({
    corridorToleranceMeters: z.number().positive().optional()
  }).optional()
});

export const optimizeRoute = async (req, res, next) => {
  try {
    const validatedData = optimizeRouteSchema.parse(req.body);
    
    // Execute route optimization pipeline
    const result = await optimizeRoutePipeline(validatedData);

    res.status(200).json({
      success: true,
      data: result
    });
  } catch (error) {
    if (error instanceof z.ZodError) {
      return res.status(400).json({
        success: false,
        error: 'Validation Error',
        details: error.errors
      });
    }
    next(error);
  }
};

const rerouteSchema = z.object({
  missionId: z.string().min(1).optional(),
  currentRoute: z.object({
    routeId: z.string(),
    encodedPolyline: z.string().optional(),
    distanceMeters: z.number().optional(),
    durationSeconds: z.number().optional()
  }).optional(),
  source: z.object({
    latitude: z.number().min(-90).max(90),
    longitude: z.number().min(-180).max(180)
  }).optional(),
  destination: z.object({
    latitude: z.number().min(-90).max(90),
    longitude: z.number().min(-180).max(180)
  }).optional(),
  resourceType: z.string().optional(),
  priority: z.enum(['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']).optional(),
  currentBackups: z.array(z.any()).optional()
});

export const reroute = async (req, res, next) => {
  try {
    const validatedData = rerouteSchema.parse(req.body);

    let { missionId, currentRoute, source, destination, resourceType, priority, currentBackups } = validatedData;

    // If missionId provided, hydrate state from database if fields missing
    if (missionId && (!currentRoute || !source || !destination)) {
      const state = await getMissionRouteState(missionId);
      if (!state) {
        return res.status(404).json({
          success: false,
          message: `Mission with ID ${missionId} not found`
        });
      }
      source = source || { latitude: state.sourceLatitude, longitude: state.sourceLongitude };
      destination = destination || { latitude: state.destinationLatitude, longitude: state.destinationLongitude };
      currentRoute = currentRoute || state.primaryRouteData;
      resourceType = resourceType || state.resourceType;
      priority = priority || state.priority;
      currentBackups = currentBackups || (state.backupRoutesData || []);
    }

    if (!currentRoute || !source || !destination) {
      return res.status(400).json({
        success: false,
        message: 'currentRoute, source, and destination are required (or a valid missionId)'
      });
    }

    const rerouteResult = await evaluateAndReroute({
      currentRoute,
      source,
      destination,
      resourceType: resourceType || 'DEFAULT',
      priority: priority || 'MEDIUM',
      missionId,
      currentBackups: currentBackups || []
    });

    res.status(200).json({
      success: true,
      data: rerouteResult
    });
  } catch (error) {
    if (error instanceof z.ZodError) {
      return res.status(400).json({
        success: false,
        error: 'Validation Error',
        details: error.errors
      });
    }
    next(error);
  }
};



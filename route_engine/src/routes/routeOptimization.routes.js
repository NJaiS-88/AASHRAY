import { Router } from 'express';
import { optimizeRoute, reroute } from '../controllers/routeOptimization.controller.js';

const router = Router();

// POST /api/routes/optimize
router.post('/optimize', optimizeRoute);

// POST /api/routes/reroute
router.post('/reroute', reroute);

export default router;


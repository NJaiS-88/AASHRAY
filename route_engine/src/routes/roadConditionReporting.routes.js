import { Router } from 'express';
import { authenticate, requireRoles } from '../middleware/auth.middleware.js';
import { submitCitizenReport, submitResponderReport } from '../controllers/roadConditionReporting.controller.js';

const router = Router();

// Citizen report endpoint (open to citizens / authenticated users)
router.post('/citizen', authenticate, submitCitizenReport);

// Responder report endpoint (RBAC restricted to RESPONDER or ADMIN)
router.post('/responder', authenticate, requireRoles(['RESPONDER', 'ADMIN']), submitResponderReport);

export default router;

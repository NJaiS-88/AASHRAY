import express from 'express';
import { config } from './config/env.js';
import { errorHandler } from './middleware/errorHandler.js';
import routeOptimizationRoutes from './routes/routeOptimization.routes.js';
import roadConditionReportingRoutes from './routes/roadConditionReporting.routes.js';

const app = express();

app.use(express.json());

app.use('/api/routes', routeOptimizationRoutes);
app.use('/api/reports', roadConditionReportingRoutes);


app.get('/health', (req, res) => {
  res.json({
    success: true,
    message: 'Route Optimisation API is running'
  });
});

app.use(errorHandler);

const PORT = config.port;

app.listen(PORT, () => {
  console.log(`Server is running on port ${PORT}`);
});

export default app;

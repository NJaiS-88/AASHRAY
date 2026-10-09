# Route Optimisation Module

## Project Purpose
Disaster-aware Route Optimisation backend module for EventOps. This module generates candidate routes, assesses real-time road conditions and detects hazards affecting primary routes, enabling secure path planning for emergency responders and missions.

## Technology Stack
- Node.js (ES Modules)
- Express
- PostgreSQL
- Prisma ORM
- Axios
- Zod
- Turf.js

## Installation
\`\`\`bash
npm install
\`\`\`

## Environment Variables
Copy `.env.example` to `.env` and fill in the required credentials.
\`\`\`bash
PORT=3000
DATABASE_URL="postgresql://user:password@localhost:5432/route_opt?schema=public"
OPENWEBNINJA_API_KEY=your_openwebninja_key
GOOGLE_MAPS_API_KEY=your_google_maps_key
\`\`\`

## Database Setup
Ensure PostgreSQL is running and your `DATABASE_URL` is set, then run:
\`\`\`bash
npx prisma generate
npx prisma db push
\`\`\`

## Running the Server
\`\`\`bash
npm run dev
\`\`\`

## Health-check Endpoint
\`\`\`
GET /health
\`\`\`
Response:
\`\`\`json
{
  "success": true,
  "message": "Route Optimisation API is running"
}
\`\`\`

## Planned Route Optimisation Architecture
- **Google Routes API**: Generates initial candidate routes.
- **OpenWeb Ninja API**: Acts as the real-time road condition engine, returning events such as `ROAD_CLOSED` and jams.
- **Flood Depth & Satellite Data**: Future enhancement for environmental analysis.
- **Primary & Backup Route Selection**: Based on route risk computation and real-time mission updates.

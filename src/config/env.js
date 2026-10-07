import dotenv from 'dotenv';

dotenv.config();

export const config = {
  port: process.env.PORT || 3000,
  databaseUrl: process.env.DATABASE_URL,
  openWebNinjaApiKey: process.env.OPENWEBNINJA_API_KEY,
  googleMapsApiKey: process.env.GOOGLE_MAPS_API_KEY,
};

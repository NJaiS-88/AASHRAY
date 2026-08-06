# AASHRAY (Crisis Assistance & Management System)

AASHRAY is a crisis reporting and management web application with multi-modal inputs (text, voice, image, GPS) and AI-driven disaster classification and semantic similarity verification.

---

## Architecture Overview

```
Frontend (Vercel - React + Vite + Tailwind)
       │
       ▼
Node.js Express Backend (Render) ──MongoDB Atlas
       │
       ▼
Python ML Microservice (Render - Flask + Scikit-Learn + SentenceTransformers)
```

---

## Deployment & Setup Guide

### 1. GitHub Repository Setup
From your project root directory (`c:\AASHRAY`):
```bash
git init
git add .
git commit -m "Initial commit - Production ready AASHRAY app"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/AASHRAY.git
git push -u origin main
```

---

### 2. Backend Service Deployment (Render)
1. Go to [Render Dashboard](https://dashboard.render.com/) -> **New** -> **Web Service**.
2. Connect your GitHub repository.
3. Settings:
   - **Root Directory**: `backend`
   - **Environment**: `Node`
   - **Build Command**: `npm install`
   - **Start Command**: `npm start`
4. **Environment Variables**:
   - `PORT`: `5000` (or leave default `$PORT`)
   - `MONGODB_URI`: `mongodb+srv://<user>:<password>@cluster0.7g29xei.mongodb.net/?appName=Cluster0`
   - `JWT_SECRET`: `<your_production_secret>`
   - `FRONTEND_URL`: `https://your-aashray-app.vercel.app`
   - `ML_SERVICE_URL`: `https://aashray-ml-service.onrender.com` (URL of step 3)

---

### 3. Python ML Microservice Deployment (Render)
1. Go to Render Dashboard -> **New** -> **Web Service**.
2. Connect your GitHub repository.
3. Settings:
   - **Root Directory**: `ml_service`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT --timeout 120`

---

### 4. Frontend Deployment (Vercel)
1. Go to [Vercel Dashboard](https://vercel.com/new) -> Import project from GitHub.
2. Select the `AASHRAY` repo.
3. Settings:
   - **Framework Preset**: `Vite`
   - **Root Directory**: `frontend`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
4. **Environment Variables**:
   - `VITE_API_URL`: `https://aashray-backend.onrender.com/api`

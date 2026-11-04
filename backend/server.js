require('dotenv').config();
const express = require('express');
const mongoose = require('mongoose');
const cors = require('cors');
const cookieParser = require('cookie-parser');
const connectDB = require('./config/db');

const authRoutes = require('./routes/auth');
const entryRoutes = require('./routes/entries');

const app = express();
const PORT = process.env.PORT || 5000;

// Connect to MongoDB
connectDB();

// Build allowed origins list from env (comma-separated)
const allowedOrigins = (process.env.FRONTEND_URL || 'http://localhost:5173')
  .split(',')
  .map(o => o.trim());

// Middleware
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ limit: '50mb', extended: true }));
app.use(cookieParser());
app.use(cors({
    origin: (origin, callback) => {
        // Allow requests with no origin (e.g. mobile/curl) or from listed origins
        if (!origin || allowedOrigins.includes(origin)) {
            callback(null, true);
        } else {
            callback(new Error(`CORS: origin ${origin} not allowed`));
        }
    },
    credentials: true,
}));

// Health check for Render (keeps service alive)
app.get('/health', (req, res) => res.status(200).json({ status: 'ok' }));

// Routes
app.use('/api/auth', authRoutes);
app.use('/api/entries', entryRoutes);

app.listen(PORT, () => {
    console.log(`Server running on port ${PORT}`);

    // Safe development test lifecycle reset (triggered when AUTO_RESET_DEV_TEST=true or --reset-test argument is passed)
    if (process.env.NODE_ENV !== 'production' && (process.env.AUTO_RESET_DEV_TEST === 'true' || process.argv.includes('--reset-test'))) {
        console.log('[Dev Lifecycle] Development mode reset flag detected. Restoring default 5 scenarios...');
        const Entry = require('./models/entry.model');
        Entry.deleteMany({
            $or: [
                { isDevTest: true },
                { conversationTitle: /test/i },
                { 'ragReport.scenario_id': /^TEST-/i },
                { 'ragReport.scenario_id': /^SCEN-/i }
            ]
        }).then(r => {
            console.log(`[Dev Lifecycle] Cleaned ${r.deletedCount} disposable test entries.`);
            const reUrl = process.env.RESOURCE_ENGINE_URL || 'http://127.0.0.1:8000';
            fetch(`${reUrl}/orchestrate/reset-test-data`, { method: 'POST' })
                .then(res => res.json())
                .then(d => console.log(`[Dev Lifecycle] Resource Engine reset: ${d.message || d.status}`))
                .catch(e => console.warn(`[Dev Lifecycle] Resource Engine reset offline: ${e.message}`));
        }).catch(err => {
            console.warn(`[Dev Lifecycle] Dev reset skipped: ${err.message}`);
        });
    }
});

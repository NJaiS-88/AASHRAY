const path = require('path');

// Ensure modules in backend/node_modules can be required regardless of cwd
module.paths.push(path.join(__dirname, '../backend/node_modules'));

try {
    require('dotenv').config({ path: path.join(__dirname, '../backend/.env') });
} catch (e) {
    // optional
}

const fs = require('fs');

if (process.env.NODE_ENV === 'production') {
    console.error('CRITICAL: Development test data reset is strictly forbidden in production mode.');
    process.exit(1);
}

async function runDevReset() {
    console.log('===============================================================');
    console.log(' AASHRAY — SAFE DEVELOPMENT/TEST LIFECYCLE RESET');
    console.log('===============================================================');

    // 1. Reset Resource Engine live orchestrations store
    const liveMissionsPath = path.join(__dirname, '../resource_engine/resource_services/database/live_orchestrations.json');
    try {
        fs.writeFileSync(liveMissionsPath, JSON.stringify([], null, 2), 'utf-8');
        console.log('[OK] Cleared disposable live missions (restored to 5 default scenarios).');
    } catch (err) {
        console.warn('! Warning clearing live_orchestrations.json:', err.message);
    }

    // 2. Reset Fleet Responders to AVAILABLE
    const respondersPath = path.join(__dirname, '../resource_engine/resource_services/database/responders.json');
    try {
        if (fs.existsSync(respondersPath)) {
            const responders = JSON.parse(fs.readFileSync(respondersPath, 'utf-8'));
            for (const r of responders) {
                r.status = 'AVAILABLE';
            }
            fs.writeFileSync(respondersPath, JSON.stringify(responders, null, 2), 'utf-8');
            console.log(`[OK] Reset ${responders.length} fleet vehicle responders to AVAILABLE.`);
        }
    } catch (err) {
        console.warn('! Warning resetting responders.json:', err.message);
    }

    // 3. Clean up disposable test entries from MongoDB using existing connectDB
    try {
        const connectDB = require('../backend/config/db');
        await connectDB();
        const Entry = require('../backend/models/entry.model');
        const mongoose = require('mongoose');
        if (mongoose.connection.readyState === 1) {
            const result = await Entry.deleteMany({
                $or: [
                    { isDevTest: true },
                    { conversationTitle: /test/i },
                    { 'ragReport.scenario_id': /^TEST-/i },
                    { 'ragReport.scenario_id': /^SCEN-/i }
                ]
            });
            console.log(`[OK] Removed ${result.deletedCount} disposable test records from database.`);
            await mongoose.disconnect();
        }
    } catch (err) {
        console.warn('! MongoDB cleanup skipped or unreachable:', err.message);
    }

    console.log('---------------------------------------------------------------');
    console.log('[OK] Safe Lifecycle Reset Complete!');
    console.log('  The 5 default scenarios are active:');
    console.log('  1. INC-FLOOD-POWAI-01');
    console.log('  2. INC-LANDSLIDE-GHATKOPAR-02');
    console.log('  3. INC-WATERLOG-KURLA-03');
    console.log('  4. INC-COLLAPSE-ANDHERI-04');
    console.log('  5. INC-CYCLONE-BANDRA-05');
    console.log('===============================================================');
}

runDevReset().catch(e => {
    console.error('Reset error:', e);
    process.exit(1);
});

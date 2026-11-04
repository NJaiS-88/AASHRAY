require('dotenv').config({ path: require('path').resolve(__dirname, '../.env') });
const mongoose = require('mongoose');
const User = require('../models/user.model');

const MONGO_URI = process.env.MONGODB_URI || process.env.MONGO_URI || 'mongodb://127.0.0.1:27017/aashray';
const ADMIN_NAME = process.env.ADMIN_NAME || 'AASHRAY Administrator';
const ADMIN_EMAIL = (process.env.ADMIN_EMAIL || 'admin@aashray.local').trim().toLowerCase();
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'Admin@Aashray2026!';

async function seedAdmin() {
  console.log(`[Admin Provision] Connecting to database at ${MONGO_URI}...`);
  await mongoose.connect(MONGO_URI, { serverSelectionTimeoutMS: 5000 });

  try {
    let adminUser = await User.findOne({ email: ADMIN_EMAIL });

    if (adminUser) {
      console.log(`[Admin Provision] Found existing user for email: ${ADMIN_EMAIL}. Updating credentials & role...`);
      adminUser.name = ADMIN_NAME;
      adminUser.role = 'admin';
      adminUser.password = ADMIN_PASSWORD; // Will be hashed by pre-save hook
      await adminUser.save();
      console.log(`[Admin Provision] Successfully updated administrator account: ${ADMIN_EMAIL}`);
    } else {
      console.log(`[Admin Provision] Creating new administrator account: ${ADMIN_EMAIL}...`);
      adminUser = await User.create({
        name: ADMIN_NAME,
        email: ADMIN_EMAIL,
        password: ADMIN_PASSWORD, // Hashed by pre-save hook
        role: 'admin'
      });
      console.log(`[Admin Provision] Successfully created administrator account: ${ADMIN_EMAIL}`);
    }

    // Verify hash verification works
    const isMatch = await adminUser.matchPassword(ADMIN_PASSWORD);
    if (!isMatch) {
      throw new Error('Password hash verification failed after provisioning.');
    }
    console.log(`[Admin Provision] Password verification confirmed: OK (role: ${adminUser.role})`);
    console.log(`[Admin Provision] Ready for Administrator Sign In via /login/admin`);
  } finally {
    await mongoose.disconnect();
    console.log('[Admin Provision] Disconnected from database.');
  }
}

seedAdmin()
  .then(() => {
    process.exit(0);
  })
  .catch((err) => {
    console.error('[Admin Provision] Error provisioning administrator account:', err);
    process.exit(1);
  });

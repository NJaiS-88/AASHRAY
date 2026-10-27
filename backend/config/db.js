const mongoose = require('mongoose');

const connectDB = async () => {
    const primaryUri = process.env.MONGODB_URI;
    const localUri = 'mongodb://127.0.0.1:27017/aashray';

    if (!primaryUri) {
        console.log('No MONGODB_URI provided. Connecting to local MongoDB at ' + localUri);
        try {
            await mongoose.connect(localUri, { serverSelectionTimeoutMS: 4000 });
            console.log('MongoDB connected successfully (local)');
            return;
        } catch (e) {
            console.warn('Could not connect to local MongoDB:', e.message);
            return;
        }
    }

    try {
        await mongoose.connect(primaryUri, { serverSelectionTimeoutMS: 4000 });
        console.log('MongoDB connected successfully to primary database');
        const User = require('../models/user.model');
        await User.syncIndexes();
        console.log('Indexes synchronized');
    } catch (error) {
        console.warn(`Primary MongoDB connection error (${error.message}). Attempting local fallback at ${localUri}...`);
        try {
            await mongoose.connect(localUri, { serverSelectionTimeoutMS: 4000 });
            console.log('MongoDB connected successfully to local fallback at ' + localUri);
            const User = require('../models/user.model');
            await User.syncIndexes();
            console.log('Indexes synchronized (local)');
        } catch (localErr) {
            console.error('MongoDB connection error:', localErr.message);
            console.warn('Server will continue running. Operations requiring DB will fail gracefully.');
        }
    }
};

module.exports = connectDB;

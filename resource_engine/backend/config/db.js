const mongoose = require('mongoose');

const connectDB = async () => {
    try {
        if (!process.env.MONGODB_URI) {
            console.log('MongoDB URI missing. Starting without DB connection for now.');
            return;
        }
        await mongoose.connect(process.env.MONGODB_URI);
        console.log('MongoDB connected successfully');
        
        // Fix for changing unique schema fields (e.g., username -> email)
        const User = require('../models/user.model');
        await User.syncIndexes();
        console.log('Indexes synchronized');
    } catch (error) {
        console.error('MongoDB connection error:', error.message);
        process.exit(1);
    }
};

module.exports = connectDB;

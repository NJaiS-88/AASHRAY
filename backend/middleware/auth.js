const jwt = require('jsonwebtoken');
const User = require('../models/user.model');

/**
 * Ensure a fallback responder user exists for local development/edge disaster dispatch.
 */
async function getOrCreateFallbackUser() {
    try {
        let user = await User.findOne({ email: 'dispatcher@aashray.local' });
        if (!user) {
            user = await User.create({
                name: 'Emergency Dispatcher',
                email: 'dispatcher@aashray.local',
                password: 'aashraypassword123',
                role: 'admin'
            });
            console.log('Created local fallback responder admin user:', user.email);
        }
        return user;
    } catch (err) {
        console.error('Error finding/creating fallback user:', err);
        return null;
    }
}

/**
 * Authentication middleware.
 * Validates JWT from cookie or Bearer Authorization header.
 */
const protect = async (req, res, next) => {
    let token = req.cookies?.jwt || (req.headers.authorization && req.headers.authorization.startsWith('Bearer ') ? req.headers.authorization.split(' ')[1] : null);

    if (token) {
        try {
            const decoded = jwt.verify(token, process.env.JWT_SECRET || 'aashray_secret_jwt_key_2026');
            const user = await User.findById(decoded.userId).select('-password');
            if (!user) {
                return res.status(401).json({ message: 'Not authorized, user not found' });
            }
            req.user = user;
            return next();
        } catch (error) {
            return res.status(401).json({ message: 'Not authorized, invalid or expired token' });
        }
    }

    return res.status(401).json({ message: 'Not authorized, no token provided' });
};

/**
 * Role-based access control for administrative endpoints.
 */
const requireAdmin = (req, res, next) => {
    if (!req.user) {
        return res.status(401).json({ message: 'Not authorized, no token' });
    }
    if (req.user.role !== 'admin') {
        return res.status(403).json({ message: 'Access denied: Administrator privileges required' });
    }
    next();
};

module.exports = { protect, requireAdmin, getOrCreateFallbackUser };

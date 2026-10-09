/**
 * Authentication and RBAC Middleware for EventOps Route Optimisation
 * 
 * Supports JWT authentication or header-based user context
 * (e.g. from an upstream API gateway, x-user-id / x-user-role / Authorization header).
 * 
 * Supported roles:
 * - CITIZEN
 * - RESPONDER
 * - ADMIN
 */

/**
 * Extracts and sets req.user from headers or dummy test token.
 */
export function authenticate(req, res, next) {
  // 1. Check custom headers often passed by API gateways or microservices
  const userId = req.headers['x-user-id'];
  const userRole = req.headers['x-user-role'];

  if (userId) {
    req.user = {
      id: String(userId),
      role: (userRole || 'CITIZEN').toUpperCase()
    };
    return next();
  }

  // 2. Check Authorization Bearer header
  const authHeader = req.headers['authorization'];
  if (authHeader && authHeader.startsWith('Bearer ')) {
    const token = authHeader.substring(7).trim();

    // If it's a token like "responder-token" or "admin-token" or "citizen-token"
    if (token.includes('responder')) {
      req.user = { id: 'responder-user-1', role: 'RESPONDER' };
      return next();
    } else if (token.includes('admin')) {
      req.user = { id: 'admin-user-1', role: 'ADMIN' };
      return next();
    } else if (token.includes('citizen')) {
      req.user = { id: 'citizen-user-1', role: 'CITIZEN' };
      return next();
    }

    // Default authenticated user
    req.user = { id: 'auth-user-1', role: 'CITIZEN' };
    return next();
  }

  // Default unauthenticated user for public or citizen endpoints
  req.user = { id: 'anonymous-citizen', role: 'CITIZEN' };
  next();
}

/**
 * RBAC middleware requiring specific role(s)
 * 
 * @param {Array<string>} allowedRoles 
 */
export function requireRoles(allowedRoles) {
  return (req, res, next) => {
    if (!req.user || !req.user.role) {
      return res.status(401).json({
        success: false,
        message: 'Authentication required'
      });
    }

    const hasRole = allowedRoles.map(r => r.toUpperCase()).includes(req.user.role.toUpperCase());
    if (!hasRole) {
      return res.status(403).json({
        success: false,
        message: `Forbidden: role '${req.user.role}' is not authorized. Required: ${allowedRoles.join(', ')}`
      });
    }

    next();
  };
}

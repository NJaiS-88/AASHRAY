import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import useAuthStore from '../store/useAuthStore';

export default function ProtectedRoute({ children, requiredRole }) {
  const user = useAuthStore((state) => state.user);
  const location = useLocation();

  if (!user) {
    // If attempting to access an admin route, send to admin login; otherwise citizen login
    const targetLogin = requiredRole === 'admin' ? '/login/admin' : '/login/citizen';
    return <Navigate to={targetLogin} state={{ from: location }} replace />;
  }

  if (requiredRole && user.role !== requiredRole) {
    if (requiredRole === 'admin' && user.role !== 'admin') {
      return <Navigate to="/unauthorized" replace />;
    }
  }

  return children;
}

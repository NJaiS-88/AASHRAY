import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import LandingPage from './pages/LandingPage';
import Login from './pages/Login';
import Signup from './pages/Signup';
import Dashboard from './pages/Dashboard';
import ResourceRouteOrchestration from './pages/ResourceRouteOrchestration';
import Unauthorized from './pages/Unauthorized';
import ProtectedRoute from './components/ProtectedRoute';

function App() {
  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        {/* Unified Role-Based Landing Page */}
        <Route path="/" element={<LandingPage />} />

        {/* Role-Based Authentication Routes */}
        <Route path="/login" element={<Login />} />
        <Route path="/login/citizen" element={<Login />} />
        <Route path="/login/admin" element={<Login />} />
        <Route path="/signup" element={<Signup />} />

        {/* Citizen Emergency Reporting Portal (Protected) */}
        <Route 
          path="/citizen" 
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          } 
        />

        {/* Administrator Operations Command Dashboard (Protected: role === 'admin') */}
        <Route 
          path="/admin" 
          element={
            <ProtectedRoute requiredRole="admin">
              <ResourceRouteOrchestration />
            </ProtectedRoute>
          } 
        />
        <Route 
          path="/admin/orchestration" 
          element={
            <ProtectedRoute requiredRole="admin">
              <ResourceRouteOrchestration />
            </ProtectedRoute>
          } 
        />
        <Route 
          path="/admin/resources" 
          element={
            <ProtectedRoute requiredRole="admin">
              <ResourceRouteOrchestration />
            </ProtectedRoute>
          } 
        />
        <Route 
          path="/admin/routes" 
          element={
            <ProtectedRoute requiredRole="admin">
              <ResourceRouteOrchestration />
            </ProtectedRoute>
          } 
        />

        {/* Access Restriction Notice */}
        <Route path="/unauthorized" element={<Unauthorized />} />

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;

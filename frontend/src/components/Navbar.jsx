import React from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { 
  ShieldAlert, 
  Activity, 
  LogOut, 
  User, 
  Compass, 
  HeartHandshake,
  Layers,
  ExternalLink,
  ChevronRight
} from 'lucide-react';
import useAuthStore from '../store/useAuthStore';
import axiosClient from '../api/axiosClient';

export default function Navbar({ currentPortal }) {
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);
  const location = useLocation();
  const navigate = useNavigate();

  const handleLogout = async () => {
    try {
      await axiosClient.post('/auth/logout');
    } catch (e) {
      // Ignore network errors on logout
    }
    logout();
    navigate('/');
  };

  const isAdmin = user?.role === 'admin';
  const isCitizenPortal = currentPortal === 'citizen' || location.pathname.startsWith('/citizen');
  const isAdminPortal = currentPortal === 'admin' || location.pathname.startsWith('/admin');

  return (
    <header 
      className="sticky top-0 z-40 w-full border-b backdrop-blur-xs transition"
      style={{ 
        background: 'rgba(255, 255, 255, 0.95)', 
        borderColor: 'var(--border)' 
      }}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-15 flex items-center justify-between gap-4">
        
        {/* Brand & Portal Identity */}
        <div className="flex items-center gap-3">
          <Link to="/" className="flex items-center gap-2 group">
            <div 
              className="w-9 h-9 rounded-xl flex items-center justify-center text-white shadow-sm transition group-hover:scale-105"
              style={{ background: 'var(--brand)' }}
            >
              <ShieldAlert className="w-5 h-5" />
            </div>
            <div className="flex flex-col">
              <span 
                className="text-base font-bold tracking-tight leading-tight"
                style={{ fontFamily: 'var(--font-headline)', color: 'var(--heading-text)' }}
              >
                AASHRAY
              </span>
              <span className="text-[10px] tracking-wide text-slate-500 font-medium">
                DISASTER INTELLIGENCE PLATFORM
              </span>
            </div>
          </Link>

          {/* Portal Badge */}
          {user && (
            <div className="hidden sm:flex items-center pl-3 border-l border-slate-200">
              {isAdminPortal ? (
                <span 
                  className="px-2.5 py-0.5 rounded-full text-xs font-semibold border flex items-center gap-1.5"
                  style={{ background: '#EEF2FF', borderColor: '#C7D2FE', color: 'var(--brand)' }}
                >
                  <Activity className="w-3.5 h-3.5 text-indigo-600" />
                  Operations Command
                </span>
              ) : (
                <span 
                  className="px-2.5 py-0.5 rounded-full text-xs font-semibold border flex items-center gap-1.5"
                  style={{ background: '#ECFDF5', borderColor: '#A7F3D0', color: '#065F46' }}
                >
                  <HeartHandshake className="w-3.5 h-3.5 text-emerald-600" />
                  Citizen Portal
                </span>
              )}
            </div>
          )}
        </div>

        {/* Central / Role Navigation */}
        {user && (
          <nav className="flex items-center gap-2">
            {isAdmin && (
              <div className="flex items-center gap-1.5 p-1 rounded-xl border bg-slate-50 border-slate-200 text-xs font-medium">
                <Link
                  to="/admin"
                  className={`px-3 py-1 rounded-lg transition flex items-center gap-1.5 ${
                    isAdminPortal 
                      ? 'bg-white shadow-2xs text-indigo-700 font-semibold' 
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  <Compass className="w-3.5 h-3.5" />
                  Operations
                </Link>
                <Link
                  to="/citizen"
                  className={`px-3 py-1 rounded-lg transition flex items-center gap-1.5 ${
                    isCitizenPortal 
                      ? 'bg-white shadow-2xs text-indigo-700 font-semibold' 
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  <HeartHandshake className="w-3.5 h-3.5" />
                  Citizen View
                </Link>
              </div>
            )}
          </nav>
        )}

        {/* User Badge & Actions */}
        <div className="flex items-center gap-3">
          {user ? (
            <div className="flex items-center gap-3">
              <div className="hidden md:flex flex-col text-right">
                <span className="text-xs font-bold text-slate-800 leading-tight">
                  {user.name || user.email}
                </span>
                <span className="text-[10px] text-slate-500 font-medium capitalize">
                  {user.role === 'admin' ? 'Authorized Administrator' : 'Verified Citizen'}
                </span>
              </div>

              <span 
                className="w-8 h-8 rounded-full border flex items-center justify-center font-bold text-xs"
                style={{ 
                  background: isAdmin ? 'var(--primary-soft)' : '#F1F5F9',
                  borderColor: isAdmin ? 'var(--brand-muted)' : '#CBD5E1',
                  color: isAdmin ? 'var(--brand)' : '#475569'
                }}
                title={`${user.name || user.email} (${user.role})`}
              >
                {(user.name ? user.name[0] : (user.email ? user.email[0] : 'U')).toUpperCase()}
              </span>

              <button
                onClick={handleLogout}
                className="p-1.5 rounded-lg border text-slate-500 hover:text-rose-600 hover:border-rose-200 hover:bg-rose-50 transition cursor-pointer flex items-center gap-1 text-xs"
                title="Log Out of AASHRAY"
              >
                <LogOut className="w-4 h-4" />
                <span className="hidden sm:inline">Logout</span>
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <Link
                to="/login/citizen"
                className="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-700 hover:bg-slate-100 transition"
              >
                Citizen Sign In
              </Link>
              <Link
                to="/login/admin"
                className="px-3.5 py-1.5 rounded-lg text-xs font-semibold text-white shadow-2xs transition"
                style={{ background: 'var(--brand)' }}
              >
                Admin Command
              </Link>
            </div>
          )}
        </div>

      </div>
    </header>
  );
}

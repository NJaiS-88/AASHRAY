import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ShieldX, ArrowLeft, LogIn, HeartHandshake } from 'lucide-react';
import useAuthStore from '../store/useAuthStore';
import Navbar from '../components/Navbar';

export default function Unauthorized() {
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);
  const navigate = useNavigate();

  const handleSwitchToAdmin = () => {
    logout();
    navigate('/login/admin');
  };

  return (
    <div className="min-h-screen flex flex-col" style={{ background: 'var(--bg-primary)' }}>
      <Navbar />

      <main className="flex-1 flex items-center justify-center p-4">
        <div 
          className="w-full max-w-md p-8 rounded-2xl border shadow-sm text-center flex flex-col items-center gap-4"
          style={{ background: 'var(--surface-white)', borderColor: 'var(--border)' }}
        >
          <div className="w-16 h-16 rounded-2xl bg-rose-50 border border-rose-200 text-rose-600 flex items-center justify-center shadow-xs">
            <ShieldX className="w-9 h-9" />
          </div>

          <div>
            <span className="text-[11px] font-bold font-mono tracking-wider uppercase text-rose-600">
              HTTP 403 Forbidden
            </span>
            <h1 className="text-xl font-bold text-slate-900 mt-1" style={{ fontFamily: 'var(--font-headline)' }}>
              Administrator Privileges Required
            </h1>
            <p className="text-xs text-slate-600 mt-2 leading-relaxed">
              Your account <strong className="text-slate-800">{user?.email || 'Current User'}</strong> is authenticated with <strong className="text-slate-800">Citizen</strong> privileges. Access to the Operations Command Dashboard, Resource Allocation Engine, and Tactical Route Routing is restricted to authorized disaster coordinators.
            </p>
          </div>

          <div className="w-full flex flex-col gap-2.5 pt-3 border-t border-slate-100">
            <Link
              to="/citizen"
              className="w-full py-2.5 px-4 rounded-xl text-xs font-semibold text-white shadow-2xs transition flex items-center justify-center gap-2"
              style={{ background: 'var(--brand)' }}
            >
              <HeartHandshake className="w-4 h-4" />
              Return to Citizen Portal
            </Link>

            <button
              onClick={handleSwitchToAdmin}
              className="w-full py-2 px-4 rounded-xl text-xs font-semibold border text-slate-700 hover:bg-slate-50 transition cursor-pointer flex items-center justify-center gap-2 border-slate-300"
            >
              <LogIn className="w-4 h-4 text-slate-500" />
              Switch to Administrator Login
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}

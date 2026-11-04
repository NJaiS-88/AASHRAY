import { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { ShieldAlert, HeartHandshake, Compass, Lock, ArrowLeft, AlertCircle } from 'lucide-react';
import axiosClient from '../api/axiosClient';
import useAuthStore from '../store/useAuthStore';

function Login() {
  const location = useLocation();
  const navigate = useNavigate();
  const setUser = useAuthStore((state) => state.setUser);
  const currentUser = useAuthStore((state) => state.user);

  // Determine initial mode based on path
  const isAdminPath = location.pathname.includes('/admin');
  const [isAdminMode, setIsAdminMode] = useState(isAdminPath);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  // Sync mode if location changes
  useEffect(() => {
    setIsAdminMode(location.pathname.includes('/admin'));
    setError('');
  }, [location.pathname]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const { data } = await axiosClient.post('/auth/login', { email, password });

      // Strict role verification if attempting admin login
      if (isAdminMode && data.role !== 'admin') {
        setError('Access denied: Account does not have administrator privileges. Please use Citizen Login.');
        setLoading(false);
        return;
      }

      setUser(data);

      if (data.role === 'admin') {
        navigate('/admin');
      } else {
        navigate('/citizen');
      }
    } catch (err) {
      setError(err.response?.data?.message || 'Authentication failed. Please verify credentials.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4 py-12" style={{ background: 'var(--bg-primary)' }}>
      
      {/* Return to Landing Link */}
      <div className="w-full max-w-md mb-4">
        <Link 
          to="/" 
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-800 transition"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Portal Overview</span>
        </Link>
      </div>

      <div className="w-full max-w-md">
        
        {/* Brand Header */}
        <div className="text-center mb-6">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl text-white shadow-sm mb-3" style={{ background: 'var(--brand)' }}>
            <ShieldAlert className="w-6 h-6" />
          </div>
          <h1 className="text-2xl font-extrabold tracking-tight text-slate-900" style={{ fontFamily: 'var(--font-headline)' }}>
            AASHRAY
          </h1>
          <p className="mt-1 text-xs text-slate-500">
            Disaster Intelligence &amp; Response Platform
          </p>
        </div>

        {/* Card */}
        <div 
          className="p-6 sm:p-8 rounded-3xl border shadow-sm"
          style={{
            background: 'var(--bg-card)',
            borderColor: 'var(--border)'
          }}
        >
          {/* Active Session Notice if already logged in */}
          {currentUser && (
            <div className="mb-5 p-3 rounded-xl bg-indigo-50/80 border border-indigo-200 text-xs text-indigo-900 flex items-center justify-between gap-2 shadow-2xs">
              <span className="truncate">
                Active session: <strong>{currentUser.email}</strong> ({currentUser.role === 'admin' ? 'Administrator' : 'Citizen'})
              </span>
              <button
                type="button"
                onClick={() => navigate(currentUser.role === 'admin' ? '/admin' : '/citizen')}
                className="font-bold underline text-indigo-700 hover:text-indigo-900 shrink-0 cursor-pointer"
              >
                Go to Dashboard &rarr;
              </button>
            </div>
          )}

          {/* Role Toggle Selector */}
          <div className="grid grid-cols-2 gap-1 p-1 bg-slate-100 rounded-xl mb-6 text-xs font-semibold">
            <button
              type="button"
              onClick={() => { setIsAdminMode(false); setError(''); }}
              className={`py-2 px-3 rounded-lg flex items-center justify-center gap-1.5 transition cursor-pointer ${
                !isAdminMode 
                  ? 'bg-white text-emerald-800 shadow-2xs font-bold' 
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <HeartHandshake className="w-3.5 h-3.5 text-emerald-600" />
              <span>Citizen Access</span>
            </button>

            <button
              type="button"
              onClick={() => { setIsAdminMode(true); setError(''); }}
              className={`py-2 px-3 rounded-lg flex items-center justify-center gap-1.5 transition cursor-pointer ${
                isAdminMode 
                  ? 'bg-white text-indigo-800 shadow-2xs font-bold' 
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <Lock className="w-3.5 h-3.5 text-indigo-600" />
              <span>Administrator</span>
            </button>
          </div>

          <div className="mb-5">
            <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
              {isAdminMode ? (
                <>
                  <Compass className="w-5 h-5 text-indigo-600" />
                  <span>Operations Command Sign In</span>
                </>
              ) : (
                <>
                  <HeartHandshake className="w-5 h-5 text-emerald-600" />
                  <span>Citizen Emergency Sign In</span>
                </>
              )}
            </h2>
            <p className="text-xs text-slate-500 mt-1">
              {isAdminMode
                ? 'Sign in with coordinator credentials to access tactical orchestration and routing.'
                : 'Sign in to report disaster incidents, view safety guidance, and track emergency responders.'}
            </p>
          </div>

          {error && (
            <div className="mb-4 px-3.5 py-2.5 rounded-xl text-xs bg-rose-50 border border-rose-200 text-rose-800 flex items-start gap-2 shadow-2xs">
              <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                {isAdminMode ? 'Coordinator Email' : 'Email Address'}
              </label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder={isAdminMode ? 'admin@aashray.local' : 'citizen@example.com'}
                className="w-full px-3.5 py-2.5 text-xs rounded-xl border border-slate-300 bg-white text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Password
              </label>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full px-3.5 py-2.5 text-xs rounded-xl border border-slate-300 bg-white text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 px-4 rounded-xl text-xs font-semibold text-white shadow-2xs transition cursor-pointer flex items-center justify-center gap-2 disabled:opacity-50"
              style={{ background: isAdminMode ? 'var(--heading-text)' : 'var(--brand)' }}
            >
              {loading ? (
                <span>Authenticating...</span>
              ) : (
                <span>{isAdminMode ? 'Authorize Command Access' : 'Sign In as Citizen'}</span>
              )}
            </button>
          </form>

          {/* Citizen Registration Link */}
          {!isAdminMode && (
            <div className="mt-5 pt-4 border-t border-slate-100 text-center text-xs text-slate-600">
              Need assistance or reporting for the first time?{' '}
              <Link to="/signup" className="font-semibold text-indigo-600 hover:text-indigo-800 transition">
                Create Citizen Account
              </Link>
            </div>
          )}

          {/* Admin Helper Notice */}
          {isAdminMode && (
            <div className="mt-5 pt-4 border-t border-slate-100 text-center text-[11px] text-slate-400">
              Administrative credentials are provided to registered regional emergency coordination offices.
            </div>
          )}
        </div>

      </div>
    </div>
  );
}

export default Login;

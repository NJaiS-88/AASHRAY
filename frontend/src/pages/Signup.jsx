import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ShieldAlert, HeartHandshake, ArrowLeft, AlertCircle, CheckCircle2 } from 'lucide-react';
import axiosClient from '../api/axiosClient';
import useAuthStore from '../store/useAuthStore';

function Signup() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const setUser = useAuthStore((state) => state.setUser);
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const { data } = await axiosClient.post('/auth/signup', { name, email, password, role: 'user' });
      setUser(data);
      navigate('/citizen');
    } catch (err) {
      setError(err.response?.data?.message || 'Registration failed. Please try again.');
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
          <div className="mb-5">
            <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
              <HeartHandshake className="w-5 h-5 text-emerald-600" />
              <span>Create Citizen Account</span>
            </h2>
            <p className="text-xs text-slate-500 mt-1">
              Join the community disaster network to report emergencies and track verified relief dispatch.
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
                Full Name
              </label>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Jane Doe"
                className="w-full px-3.5 py-2.5 text-xs rounded-xl border border-slate-300 bg-white text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Email Address
              </label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="citizen@example.com"
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
              className="w-full py-2.5 px-4 rounded-xl text-xs font-semibold text-white shadow-2xs transition cursor-pointer flex items-center justify-center gap-2 disabled:opacity-50 mt-2"
              style={{ background: 'var(--brand)' }}
            >
              {loading ? 'Creating Account...' : 'Register Account'}
            </button>
          </form>

          <div className="mt-5 pt-4 border-t border-slate-100 text-center text-xs text-slate-600">
            Already have an account?{' '}
            <Link to="/login/citizen" className="font-semibold text-indigo-600 hover:text-indigo-800 transition">
              Sign In
            </Link>
          </div>
        </div>

      </div>
    </div>
  );
}

export default Signup;

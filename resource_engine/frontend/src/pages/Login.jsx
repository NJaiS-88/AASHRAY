import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import axiosClient from '../api/axiosClient';
import useAuthStore from '../store/useAuthStore';

function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const setUser = useAuthStore((state) => state.setUser);
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const { data } = await axiosClient.post('/auth/login', { email, password });
      setUser(data);
      navigate('/orchestration');
    } catch (err) {
      setError(err.response?.data?.message || 'Login failed');
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center px-4" style={{ background: 'var(--bg-primary)' }}>
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold tracking-tight" style={{ fontFamily: 'var(--font-headline)', color: 'var(--text-primary)' }}>
            AASHRAY
          </h1>
          <p className="mt-2 text-sm" style={{ color: 'var(--text-tertiary)' }}>
            Resource &amp; Route Logistics Engine
          </p>
        </div>

        <div className="p-6" style={{
          background: 'var(--bg-card)',
          borderRadius: 'var(--radius-card)',
          border: '1px solid var(--border)',
          boxShadow: 'var(--shadow-card)'
        }}>
          <h2 className="text-lg font-semibold mb-5" style={{ color: 'var(--text-primary)' }}>Sign in</h2>

          {error && (
            <div className="mb-4 px-3 py-2 text-sm" style={{
              background: '#FEF2F2',
              color: 'var(--severity-critical)',
              borderRadius: 'var(--radius-input)',
              border: '1px solid #FECACA'
            }}>
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div>
              <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--text-secondary)' }}>Email</label>
              <input
                type="email"
                placeholder="you@example.com"
                className="w-full px-3.5 py-2.5 text-sm outline-none transition-colors"
                style={{
                  background: 'var(--bg-input)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-input)',
                  color: 'var(--text-primary)'
                }}
                onFocus={(e) => e.target.style.borderColor = 'var(--brand)'}
                onBlur={(e) => e.target.style.borderColor = 'var(--border)'}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--text-secondary)' }}>Password</label>
              <input
                type="password"
                placeholder="Enter password"
                className="w-full px-3.5 py-2.5 text-sm outline-none transition-colors"
                style={{
                  background: 'var(--bg-input)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-input)',
                  color: 'var(--text-primary)'
                }}
                onFocus={(e) => e.target.style.borderColor = 'var(--brand)'}
                onBlur={(e) => e.target.style.borderColor = 'var(--border)'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            <button
              type="submit"
              className="w-full py-2.5 text-sm font-semibold transition-colors cursor-pointer"
              style={{
                background: 'var(--brand)',
                color: 'var(--text-on-brand)',
                borderRadius: 'var(--radius-button)',
                border: 'none'
              }}
              onMouseOver={(e) => e.currentTarget.style.background = 'var(--brand-hover)'}
              onMouseOut={(e) => e.currentTarget.style.background = 'var(--brand)'}
            >
              Sign in
            </button>
          </form>

          <p className="mt-5 text-center text-sm" style={{ color: 'var(--text-tertiary)' }}>
            Need an account?{' '}
            <Link to="/signup" className="font-medium hover:underline" style={{ color: 'var(--brand)' }}>
              Create account
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}

export default Login;

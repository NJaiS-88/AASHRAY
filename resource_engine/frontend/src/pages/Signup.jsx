import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import axiosClient from '../api/axiosClient';
import useAuthStore from '../store/useAuthStore';

function Signup() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('user');
  const [error, setError] = useState('');
  const setUser = useAuthStore((state) => state.setUser);
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const { data } = await axiosClient.post('/auth/signup', { name, email, password, role });
      setUser(data);
      navigate('/orchestration');
    } catch (err) {
      setError(err.response?.data?.message || 'Signup failed');
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
          <h2 className="text-lg font-semibold mb-5" style={{ color: 'var(--text-primary)' }}>Create account</h2>

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
              <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--text-secondary)' }}>Name</label>
              <input
                type="text"
                placeholder="Your name"
                className="w-full px-3.5 py-2.5 text-sm outline-none transition-colors"
                style={{
                  background: 'var(--bg-input)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-input)',
                  color: 'var(--text-primary)'
                }}
                onFocus={(e) => e.target.style.borderColor = 'var(--brand)'}
                onBlur={(e) => e.target.style.borderColor = 'var(--border)'}
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </div>
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
                placeholder="Choose a password"
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
            <div>
              <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--text-secondary)' }}>Account Role</label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setRole('user')}
                  className="py-2 px-3 text-xs font-medium rounded-lg border transition-all cursor-pointer text-center"
                  style={{
                    background: role === 'user' ? 'var(--brand-light)' : 'var(--bg-input)',
                    borderColor: role === 'user' ? 'var(--brand)' : 'var(--border)',
                    color: role === 'user' ? 'var(--brand)' : 'var(--text-secondary)'
                  }}
                >
                  Citizen Reporter
                </button>
                <button
                  type="button"
                  onClick={() => setRole('admin')}
                  className="py-2 px-3 text-xs font-medium rounded-lg border transition-all cursor-pointer text-center"
                  style={{
                    background: role === 'admin' ? 'var(--brand-light)' : 'var(--bg-input)',
                    borderColor: role === 'admin' ? 'var(--brand)' : 'var(--border)',
                    color: role === 'admin' ? 'var(--brand)' : 'var(--text-secondary)'
                  }}
                >
                  Operations Admin
                </button>
              </div>
            </div>
            <button
              type="submit"
              className="w-full py-2.5 text-sm font-semibold transition-colors cursor-pointer mt-1"
              style={{
                background: 'var(--brand)',
                color: 'var(--text-on-brand)',
                borderRadius: 'var(--radius-button)',
                border: 'none'
              }}
              onMouseOver={(e) => e.currentTarget.style.background = 'var(--brand-hover)'}
              onMouseOut={(e) => e.currentTarget.style.background = 'var(--brand)'}
            >
              Create account
            </button>
          </form>

          <p className="mt-5 text-center text-sm" style={{ color: 'var(--text-tertiary)' }}>
            Already have an account?{' '}
            <Link to="/login" className="font-medium hover:underline" style={{ color: 'var(--brand)' }}>
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}

export default Signup;

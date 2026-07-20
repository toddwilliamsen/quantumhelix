import React, { useState } from 'react';
import { Activity, Lock } from 'lucide-react';

function Login({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    
    try {
      const res = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });
      
      const data = await res.json();
      if (res.ok) {
        onLogin(data.token, data.role, data.username);
      } else {
        setError(data.message || 'Invalid credentials');
      }
    } catch (err) {
      setError('Network error. Is the backend running?');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'var(--bg-color)' }}>
      <div className="card" style={{ width: '100%', maxWidth: '400px', padding: '2.5rem' }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', marginBottom: '2rem' }}>
          <Activity color="var(--primary)" size={48} style={{ marginBottom: '1rem' }} />
          <h2 style={{ margin: 0, fontSize: '1.5rem' }}>Quantum Helix</h2>
          <p style={{ color: 'var(--text-secondary)', margin: '0.5rem 0 0 0' }}>Sign in to the SOC Console</p>
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          {error && (
            <div style={{ backgroundColor: 'var(--danger-bg)', color: 'var(--danger)', padding: '0.75rem', borderRadius: '0.5rem', fontSize: '0.875rem', textAlign: 'center' }}>
              {error}
            </div>
          )}
          
          <div className="control-group">
            <label className="control-label">Username</label>
            <input 
              type="text" 
              value={username}
              onChange={e => setUsername(e.target.value)}
              style={{ padding: '0.75rem', borderRadius: '0.5rem', border: '1px solid var(--border-color)', outline: 'none' }}
              required
            />
          </div>

          <div className="control-group">
            <label className="control-label">Password</label>
            <input 
              type="password" 
              value={password}
              onChange={e => setPassword(e.target.value)}
              style={{ padding: '0.75rem', borderRadius: '0.5rem', border: '1px solid var(--border-color)', outline: 'none' }}
              required
            />
          </div>

          <button 
            type="submit" 
            className="btn btn-primary" 
            style={{ padding: '0.75rem', marginTop: '0.5rem', fontSize: '1rem' }}
            disabled={loading}
          >
            {loading ? 'Authenticating...' : <><Lock size={18} /> Sign In</>}
          </button>
        </form>
      </div>
    </div>
  );
}

export default Login;

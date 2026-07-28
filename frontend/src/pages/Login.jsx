import React, { useState } from 'react';
import { Activity, Lock, Key, Smartphone } from 'lucide-react';
import { startAuthentication } from '@simplewebauthn/browser';

function Login({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  
  // MFA State
  const [mfaRequired, setMfaRequired] = useState(false);
  const [tempToken, setTempToken] = useState(null);
  const [totpEnabled, setTotpEnabled] = useState(false);
  const [webauthnEnabled, setWebauthnEnabled] = useState(false);
  const [totpCode, setTotpCode] = useState('');

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
        if (data.mfa_required) {
          setMfaRequired(true);
          setTempToken(data.temp_token);
          setTotpEnabled(data.totp_enabled);
          setWebauthnEnabled(data.webauthn_enabled);
        } else {
          onLogin(data.token, data.role, data.username);
        }
      } else {
        setError(data.message || 'Invalid credentials');
      }
    } catch (err) {
      setError('Network error. Is the backend running?');
    } finally {
      setLoading(false);
    }
  };

  const handleTotpSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    
    try {
      const res = await fetch('/api/login/mfa', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ temp_token: tempToken, type: 'totp', code: totpCode })
      });
      
      const data = await res.json();
      if (res.ok) {
        onLogin(data.token, data.role, data.username);
      } else {
        setError(data.message || 'Invalid code');
      }
    } catch (err) {
      setError('Network error.');
    } finally {
      setLoading(false);
    }
  };

  const handleWebAuthnLogin = async () => {
    setLoading(true);
    setError('');
    
    try {
      const optRes = await fetch('/api/login/webauthn-options', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ temp_token: tempToken })
      });
      const options = await optRes.json();
      
      if (!optRes.ok) {
        throw new Error(options.message);
      }

      let asseResp;
      try {
        asseResp = await startAuthentication(options);
      } catch (e) {
        throw new Error('Hardware key interaction failed or cancelled.');
      }

      const verRes = await fetch('/api/login/mfa', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ temp_token: tempToken, type: 'webauthn', credential: asseResp })
      });

      const verData = await verRes.json();
      if (verRes.ok) {
        onLogin(verData.token, verData.role, verData.username);
      } else {
        throw new Error(verData.message);
      }
    } catch (err) {
      setError(err.message || 'Hardware key error');
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
          <p style={{ color: 'var(--text-secondary)', margin: '0.5rem 0 0 0' }}>{mfaRequired ? 'Two-Factor Authentication' : 'Sign in to the SOC Console'}</p>
        </div>

        {error && (
          <div style={{ backgroundColor: 'var(--danger-bg)', color: 'var(--danger)', padding: '0.75rem', borderRadius: '0.5rem', fontSize: '0.875rem', textAlign: 'center', marginBottom: '1.25rem' }}>
            {error}
          </div>
        )}

        {!mfaRequired ? (
          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
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
            <button type="submit" className="btn btn-primary" style={{ padding: '0.75rem', marginTop: '0.5rem', fontSize: '1rem' }} disabled={loading}>
              {loading ? 'Authenticating...' : <><Lock size={18} /> Sign In</>}
            </button>
          </form>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            {webauthnEnabled && (
              <button 
                onClick={handleWebAuthnLogin}
                className="btn btn-primary" 
                style={{ padding: '0.75rem', fontSize: '1rem', width: '100%', display: 'flex', justifyContent: 'center', gap: '0.5rem' }}
                disabled={loading}
              >
                <Key size={18} /> Use Hardware Key
              </button>
            )}

            {totpEnabled && (
              <form onSubmit={handleTotpSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', marginTop: webauthnEnabled ? '1rem' : 0 }}>
                {webauthnEnabled && <div style={{ textAlign: 'center', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>— or use authenticator app —</div>}
                <div className="control-group">
                  <label className="control-label">6-Digit Code</label>
                  <input 
                    type="text" 
                    value={totpCode}
                    onChange={e => setTotpCode(e.target.value)}
                    placeholder="000000"
                    style={{ padding: '0.75rem', borderRadius: '0.5rem', border: '1px solid var(--border-color)', outline: 'none', textAlign: 'center', letterSpacing: '0.25em', fontSize: '1.2rem' }}
                    required
                    maxLength={6}
                  />
                </div>
                <button type="submit" className="btn btn-secondary" style={{ padding: '0.75rem', fontSize: '1rem' }} disabled={loading}>
                  {loading ? 'Verifying...' : <><Smartphone size={18} /> Verify Code</>}
                </button>
              </form>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default Login;

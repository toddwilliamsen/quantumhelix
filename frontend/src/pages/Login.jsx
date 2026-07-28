import React, { useState } from 'react';
import { Lock, Key, Smartphone } from 'lucide-react';
import { startAuthentication } from '@simplewebauthn/browser';

function Login({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

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
          onLogin(data.token, data.role, data.username, data.must_change_password);
        }
      } else {
        setError(data.message || 'Invalid credentials');
      }
    } catch {
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
        onLogin(data.token, data.role, data.username, data.must_change_password);
      } else {
        setError(data.message || 'Invalid code');
      }
    } catch {
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
        asseResp = await startAuthentication({ optionsJSON: options });
      } catch {
        throw new Error('Hardware key interaction failed or cancelled.');
      }

      const verRes = await fetch('/api/login/mfa', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ temp_token: tempToken, type: 'webauthn', credential: asseResp })
      });

      const verData = await verRes.json();
      if (verRes.ok) {
        onLogin(verData.token, verData.role, verData.username, verData.must_change_password);
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
    <div className="login-page">
      <aside className="login-aside" aria-label="Product">
        <div className="login-aside__content">
          <p className="login-aside__eyebrow">Hybrid quantum-classical detection</p>
          <p className="login-aside__brand">Quantum Helix</p>
          <h2>Cloud threat detection with explainable model consensus.</h2>
          <p>
            Monitor normalized telemetry, investigate detector disagreement, and coordinate
            response workflows from one analyst console.
          </p>
        </div>
      </aside>

      <section className="login-panel" aria-labelledby="login-heading">
        <div className="login-form">
          <h1 id="login-heading" className="login-heading">
            {mfaRequired ? 'Verify your identity' : 'Sign in to the console'}
          </h1>
          <p className="login-subtitle">
            {mfaRequired
              ? 'Complete the configured second factor to continue.'
              : 'Use your organization credentials to access triage, cases, and analytics.'}
          </p>

          {error && <div className="form-error" role="alert">{error}</div>}

          {!mfaRequired ? (
            <form onSubmit={handleSubmit} className="form-stack">
              <div className="control-group">
                <label className="control-label" htmlFor="username">Username</label>
                <input
                  id="username"
                  type="text"
                  autoComplete="username"
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  required
                  autoFocus
                />
              </div>
              <div className="control-group">
                <label className="control-label" htmlFor="password">Password</label>
                <input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  required
                />
              </div>
              <button type="submit" className="btn btn-primary" disabled={loading}>
                <Lock size={16} /> {loading ? 'Signing in…' : 'Sign in'}
              </button>
            </form>
          ) : (
            <div className="form-stack">
              {webauthnEnabled && (
                <button
                  onClick={handleWebAuthnLogin}
                  className="btn btn-primary"
                  disabled={loading}
                >
                  <Key size={16} /> Use security key
                </button>
              )}

              {totpEnabled && (
                <form onSubmit={handleTotpSubmit} className="form-stack">
                  {webauthnEnabled && (
                    <span className="control-label">Or use an authenticator code</span>
                  )}
                  <div className="control-group">
                    <label className="control-label" htmlFor="totp-code">Six-digit code</label>
                    <input
                      id="totp-code"
                      type="text"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      value={totpCode}
                      onChange={e => setTotpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                      required
                      autoFocus
                    />
                  </div>
                  <button type="submit" className="btn btn-secondary" disabled={loading || totpCode.length !== 6}>
                    <Smartphone size={16} /> {loading ? 'Verifying…' : 'Verify code'}
                  </button>
                </form>
              )}
              <button
                type="button"
                className="link-button"
                style={{ color: 'var(--text-secondary)' }}
                onClick={() => {
                  setMfaRequired(false);
                  setTempToken(null);
                  setTotpCode('');
                  setError('');
                }}
              >
                Back to sign in
              </button>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

export default Login;

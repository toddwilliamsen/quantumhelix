import React, { useState, useEffect, useCallback } from 'react';
import toast from 'react-hot-toast';
import { startRegistration } from '@simplewebauthn/browser';
import { apiFetch } from '../api';
import { MIN_PASSWORD_LENGTH, ROLE_LABELS } from '../roles';

function Account({ token }) {
  const username = localStorage.getItem('quantum_username');
  const role = localStorage.getItem('quantum_role');

  const [loading, setLoading] = useState(false);
  const [mfaStatus, setMfaStatus] = useState({ totp_enabled: false, webauthn_enabled: false });
  const [qrCode, setQrCode] = useState(null);
  const [totpCode, setTotpCode] = useState('');

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');

  const fetchMfaStatus = useCallback(async () => {
    try {
      const data = await apiFetch('/api/mfa/status', { token });
      setMfaStatus(data);
    } catch (e) {
      console.error(e);
    }
  }, [token]);

  useEffect(() => { fetchMfaStatus(); }, [fetchMfaStatus]);

  const changePassword = async (e) => {
    e.preventDefault();
    if (newPassword !== confirmPassword) {
      toast.error('New passwords do not match');
      return;
    }
    setLoading(true);
    try {
      const data = await apiFetch('/api/me/password', {
        method: 'POST',
        token,
        json: { current_password: currentPassword, new_password: newPassword },
      });
      if (data.token) {
        localStorage.setItem('quantum_token', data.token);
        localStorage.removeItem('quantum_must_change_password');
        window.dispatchEvent(new CustomEvent('quantum:token', { detail: data.token }));
      }
      toast.success('Password updated');
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (e) {
      toast.error(e.message || 'Failed to update password');
    } finally {
      setLoading(false);
    }
  };

  const setupTotp = async () => {
    setLoading(true);
    try {
      const data = await apiFetch('/api/mfa/setup-totp', { method: 'POST', token });
      setQrCode(data.qr_code);
    } catch (e) {
      toast.error(e.message || 'Failed to start authenticator setup');
    } finally {
      setLoading(false);
    }
  };

  const verifyTotp = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await apiFetch('/api/mfa/verify-totp', { method: 'POST', token, json: { code: totpCode } });
      toast.success('Authenticator app enabled');
      setQrCode(null);
      setTotpCode('');
      fetchMfaStatus();
    } catch (e) {
      toast.error(e.message || 'Invalid code');
    } finally {
      setLoading(false);
    }
  };

  const registerHardwareKey = async () => {
    setLoading(true);
    try {
      const options = await apiFetch('/api/mfa/register-webauthn', { method: 'POST', token });
      let attResp;
      try {
        attResp = await startRegistration({ optionsJSON: options });
      } catch {
        toast.error('Security key registration cancelled');
        return;
      }
      await apiFetch('/api/mfa/verify-webauthn-registration', { method: 'POST', token, json: attResp });
      toast.success('Security key registered');
      fetchMfaStatus();
    } catch (e) {
      toast.error(e.message || 'Failed to register security key');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">My account</h1>
        <p className="page-subtitle">
          Signed in as <strong>{username}</strong> · {ROLE_LABELS[role] || role}
        </p>
      </div>

      {localStorage.getItem('quantum_must_change_password') === '1' && (
        <div className="notice-warning" style={{ maxWidth: '760px', marginBottom: '1rem' }}>
          You must set a new password before using the rest of the console.
        </div>
      )}

      <div className="card" style={{ maxWidth: '760px' }}>
        <h3 style={{ marginTop: 0 }}>Password</h3>
        <p className="settings-hint" style={{ marginBottom: '1.5rem' }}>
          Choose something at least {MIN_PASSWORD_LENGTH} characters that you do not use elsewhere.
        </p>
        <form className="account-form" onSubmit={changePassword}>
          <div className="account-field">
            <label className="control-label" htmlFor="current-password">Current password</label>
            <input
              id="current-password"
              type="password"
              className="form-control"
              autoComplete="current-password"
              value={currentPassword}
              onChange={e => setCurrentPassword(e.target.value)}
              required
            />
          </div>
          <div className="account-field">
            <label className="control-label" htmlFor="new-password">New password</label>
            <input
              id="new-password"
              type="password"
              className="form-control"
              autoComplete="new-password"
              minLength={MIN_PASSWORD_LENGTH}
              value={newPassword}
              onChange={e => setNewPassword(e.target.value)}
              required
            />
          </div>
          <div className="account-field">
            <label className="control-label" htmlFor="confirm-password">Confirm new password</label>
            <input
              id="confirm-password"
              type="password"
              className="form-control"
              autoComplete="new-password"
              minLength={MIN_PASSWORD_LENGTH}
              value={confirmPassword}
              onChange={e => setConfirmPassword(e.target.value)}
              required
            />
          </div>
          <button type="submit" className="btn btn-primary" disabled={loading}>Update password</button>
        </form>
      </div>

      <div className="card" style={{ maxWidth: '760px' }}>
        <h3 style={{ marginTop: 0 }}>Multi-factor authentication</h3>
        <p className="settings-hint" style={{ marginBottom: '1.5rem' }}>
          Required at sign-in once enabled. An administrator can clear your enrollment if you lose your device.
        </p>

        <div className="account-panels">
          <div className="account-panel">
            <div className="account-panel-header">
              <div>
                <h4>Authenticator app (TOTP)</h4>
                <p className="settings-hint">Six-digit codes from an app such as Google Authenticator, 1Password, or Authy.</p>
              </div>
              <span className={`status-pill ${mfaStatus.totp_enabled ? 'is-success' : ''}`}>
                {mfaStatus.totp_enabled ? 'Enabled' : 'Not enabled'}
              </span>
            </div>

            {!mfaStatus.totp_enabled && !qrCode && (
              <button className="btn btn-secondary" onClick={setupTotp} disabled={loading}>
                Set up authenticator
              </button>
            )}

            {qrCode && (
              <div className="totp-setup">
                <img
                  src={`data:image/png;base64,${qrCode}`}
                  alt="Authenticator setup QR code"
                  className="totp-qr"
                />
                <form onSubmit={verifyTotp} className="totp-verify">
                  <label className="control-label" htmlFor="totp-code">
                    Scan the code, then enter the six digits shown in your app
                  </label>
                  <input
                    id="totp-code"
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    className="form-control totp-input"
                    value={totpCode}
                    onChange={e => setTotpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                    placeholder="000000"
                    maxLength={6}
                  />
                  <div className="account-actions">
                    <button type="submit" className="btn btn-primary" disabled={loading || totpCode.length !== 6}>
                      Verify and enable
                    </button>
                    <button type="button" className="btn btn-secondary" onClick={() => { setQrCode(null); setTotpCode(''); }}>
                      Cancel
                    </button>
                  </div>
                </form>
              </div>
            )}
          </div>

          <div className="account-panel">
            <div className="account-panel-header">
              <div>
                <h4>Security key (WebAuthn)</h4>
                <p className="settings-hint">A hardware key, Touch ID, or Windows Hello on this device.</p>
              </div>
              <span className={`status-pill ${mfaStatus.webauthn_enabled ? 'is-success' : ''}`}>
                {mfaStatus.webauthn_enabled ? 'Registered' : 'Not registered'}
              </span>
            </div>
            <button className="btn btn-secondary" onClick={registerHardwareKey} disabled={loading}>
              {mfaStatus.webauthn_enabled ? 'Register another key' : 'Register security key'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Account;

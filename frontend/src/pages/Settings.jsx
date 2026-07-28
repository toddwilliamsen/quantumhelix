import React, { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import { startRegistration } from '@simplewebauthn/browser';

function Settings({ token }) {
  const [rules, setRules] = useState([]);
  const [ruleType, setRuleType] = useState('identity');
  const [ruleValue, setRuleValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('detection');
  
  // MFA State
  const [mfaStatus, setMfaStatus] = useState({ totp_enabled: false, webauthn_enabled: false });
  const [qrCode, setQrCode] = useState(null);
  const [totpCode, setTotpCode] = useState('');
  
  // SOAR State
  const [playbooks, setPlaybooks] = useState([]);
  const [pbField, setPbField] = useState('score');
  const [pbOp, setPbOp] = useState('>');
  const [pbVal, setPbVal] = useState('0.85');
  const [pbAction, setPbAction] = useState('auto_isolate');

  // Audit State
  const [auditLogs, setAuditLogs] = useState([]);

  // Multi-tenant & RBAC State
  const role = localStorage.getItem('quantum_role');
  const [tenants, setTenants] = useState([]);
  const [users, setUsers] = useState([]);
  const [newTenantName, setNewTenantName] = useState('');
  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newUserRole, setNewUserRole] = useState('TIER_1');
  const [newUserTenant, setNewUserTenant] = useState('');

  const fetchTenants = async () => {
    try {
      const res = await fetch('/api/tenants', { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) setTenants(await res.json());
    } catch (e) { console.error(e); }
  };
  
  const fetchUsers = async () => {
    try {
      const res = await fetch('/api/users', { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) setUsers(await res.json());
    } catch (e) { console.error(e); }
  };
  
  useEffect(() => {
    if (role === 'SUPER_ADMIN') fetchTenants();
    if (role === 'SUPER_ADMIN' || role === 'TENANT_ADMIN') fetchUsers();
  }, [role]);

  const createTenant = async (e) => {
    e.preventDefault();
    try {
      const res = await fetch('/api/tenants', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ name: newTenantName })
      });
      if (res.ok) {
        toast.success("Tenant created");
        setNewTenantName('');
        fetchTenants();
      }
    } catch (e) { toast.error("Failed to create tenant"); }
  };
  
  const toggleCompliance = async (tenantId) => {
    try {
      const res = await fetch(`/api/tenants/${tenantId}/compliance`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        toast.success("Compliance mode updated");
        fetchTenants();
      }
    } catch (e) { toast.error("Failed to update compliance"); }
  };

  const createUser = async (e) => {
    e.preventDefault();
    try {
      const res = await fetch('/api/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ username: newUsername, password: newPassword, role: newUserRole, tenant_id: newUserTenant })
      });
      if (res.ok) {
        toast.success("User created");
        setNewUsername('');
        setNewPassword('');
        fetchUsers();
      }
    } catch (e) { toast.error("Failed to create user"); }
  };


  useEffect(() => {
    fetchRules();
    fetchMfaStatus();
    fetchPlaybooks();
    fetchAuditLogs();
  }, []);

  const fetchPlaybooks = async () => {
    try {
      const res = await fetch('/api/playbooks', { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) setPlaybooks(await res.json());
    } catch (e) { console.error(e); }
  };

  const fetchAuditLogs = async () => {
    try {
      const res = await fetch('/api/audit', { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) setAuditLogs(await res.json());
    } catch (e) { console.error(e); }
  };

  const fetchMfaStatus = async () => {
    try {
      const res = await fetch('/api/mfa/status', { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) {
        const data = await res.json();
        setMfaStatus(data);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const fetchRules = async () => {
    try {
      const res = await fetch('/api/rules', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      setRules(data);
    } catch (e) {
      console.error(e);
      toast.error('Failed to load suppression rules');
    }
  };

  const addRule = async (e) => {
    e.preventDefault();
    if (!ruleValue.trim()) return;
    
    setLoading(true);
    try {
      const res = await fetch('/api/rules', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ rule_type: ruleType, value: ruleValue })
      });
      if (res.ok) {
        toast.success('Suppression rule added');
        setRuleValue('');
        fetchRules();
      } else {
        toast.error('Failed to add rule');
      }
    } catch (e) {
      console.error(e);
      toast.error('An error occurred');
    } finally {
      setLoading(false);
    }
  };

  const deleteRule = async (id) => {
    try {
      const res = await fetch(`/api/rules/${id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        toast.success('Rule removed');
        fetchRules();
      } else {
        toast.error('Failed to remove rule');
      }
    } catch (e) {
      console.error(e);
      toast.error('An error occurred');
    }
  };

  const setupTotp = async () => {
    try {
      setLoading(true);
      const res = await fetch('/api/mfa/setup-totp', { method: 'POST', headers: { 'Authorization': `Bearer ${token}` } });
      const data = await res.json();
      setQrCode(data.qr_code);
    } catch (e) {
      toast.error('Failed to setup TOTP');
    } finally {
      setLoading(false);
    }
  };

  const verifyTotp = async (e) => {
    e.preventDefault();
    try {
      setLoading(true);
      const res = await fetch('/api/mfa/verify-totp', { 
        method: 'POST', 
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ code: totpCode })
      });
      if (res.ok) {
        toast.success('Authenticator App configured successfully!');
        setQrCode(null);
        fetchMfaStatus();
      } else {
        toast.error('Invalid TOTP Code');
      }
    } catch (e) {
      toast.error('Failed to verify TOTP');
    } finally {
      setLoading(false);
    }
  };

  const registerHardwareKey = async () => {
    try {
      setLoading(true);
      const optRes = await fetch('/api/mfa/register-webauthn', { method: 'POST', headers: { 'Authorization': `Bearer ${token}` } });
      const options = await optRes.json();
      
      let attResp;
      try {
        attResp = await startRegistration(options);
      } catch (e) {
        toast.error('Hardware key registration cancelled.');
        return;
      }

      const verRes = await fetch('/api/mfa/verify-webauthn-registration', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify(attResp)
      });
      
      if (verRes.ok) {
        toast.success('Hardware key registered successfully!');
        fetchMfaStatus();
      } else {
        toast.error('Failed to verify hardware key');
      }
    } catch (e) {
      toast.error('Error during hardware key registration');
    } finally {
      setLoading(false);
    }
  };

  const addPlaybook = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await fetch('/api/playbooks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ condition_field: pbField, condition_operator: pbOp, condition_value: pbVal, action: pbAction })
      });
      if (res.ok) {
        toast.success('Playbook created');
        fetchPlaybooks();
      }
    } catch (e) {
      toast.error('Failed to create playbook');
    } finally {
      setLoading(false);
    }
  };

  const deletePlaybook = async (id) => {
    try {
      const res = await fetch(`/api/playbooks/${id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        toast.success('Playbook removed');
        fetchPlaybooks();
      }
    } catch (e) {
      toast.error('Failed to remove playbook');
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Settings & Rules</h1>
        <p className="page-subtitle">Manage system configuration and alert suppression rules.</p>
      </div>

      <div style={{ display: 'flex', gap: '1rem', marginBottom: '2rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem', overflowX: 'auto' }}>
        <button 
          className={`btn ${activeTab === 'detection' ? 'btn-primary' : ''}`}
          onClick={() => setActiveTab('detection')}
          style={{ whiteSpace: 'nowrap', background: activeTab === 'detection' ? 'var(--primary)' : 'transparent', color: activeTab === 'detection' ? 'white' : 'var(--text-secondary)', border: 'none', boxShadow: 'none' }}
        >
          Detection Engineering (Rules)
        </button>
        <button 
          className={`btn ${activeTab === 'playbooks' ? 'btn-primary' : ''}`}
          onClick={() => setActiveTab('playbooks')}
          style={{ whiteSpace: 'nowrap', background: activeTab === 'playbooks' ? 'var(--primary)' : 'transparent', color: activeTab === 'playbooks' ? 'white' : 'var(--text-secondary)', border: 'none', boxShadow: 'none' }}
        >
          SOAR Playbooks
        </button>
        <button 
          className={`btn ${activeTab === 'audit' ? 'btn-primary' : ''}`}
          onClick={() => setActiveTab('audit')}
          style={{ whiteSpace: 'nowrap', background: activeTab === 'audit' ? 'var(--primary)' : 'transparent', color: activeTab === 'audit' ? 'white' : 'var(--text-secondary)', border: 'none', boxShadow: 'none' }}
        >
          Audit Logs
        </button>
        <button 
          className={`btn ${activeTab === 'security' ? 'btn-primary' : ''}`}
          onClick={() => setActiveTab('security')}
          style={{ whiteSpace: 'nowrap', background: activeTab === 'security' ? 'var(--primary)' : 'transparent', color: activeTab === 'security' ? 'white' : 'var(--text-secondary)', border: 'none', boxShadow: 'none' }}
        >
          Security & MFA
        </button>
        <button 
          className={`btn ${activeTab === 'system' ? 'btn-primary' : ''}`}
          onClick={() => setActiveTab('system')}
          style={{ whiteSpace: 'nowrap', background: activeTab === 'system' ? 'var(--primary)' : 'transparent', color: activeTab === 'system' ? 'white' : 'var(--text-secondary)', border: 'none', boxShadow: 'none' }}
        >
          System Configuration
        </button>

        {role === 'SUPER_ADMIN' && (
          <button 
            className={`btn ${activeTab === 'tenants' ? 'btn-primary' : ''}`}
            onClick={() => setActiveTab('tenants')}
            style={{ whiteSpace: 'nowrap', background: activeTab === 'tenants' ? 'var(--primary)' : 'transparent', color: activeTab === 'tenants' ? 'white' : 'var(--text-secondary)', border: 'none', boxShadow: 'none' }}
          >
            Tenants (MSSP)
          </button>
        )}
        {(role === 'SUPER_ADMIN' || role === 'TENANT_ADMIN') && (
          <button 
            className={`btn ${activeTab === 'users' ? 'btn-primary' : ''}`}
            onClick={() => setActiveTab('users')}
            style={{ whiteSpace: 'nowrap', background: activeTab === 'users' ? 'var(--primary)' : 'transparent', color: activeTab === 'users' ? 'white' : 'var(--text-secondary)', border: 'none', boxShadow: 'none' }}
          >
            User Access
          </button>
        )}
        <button 
          className={`btn ${activeTab === 'sources' ? 'btn-primary' : ''}`}
          onClick={() => setActiveTab('sources')}
          style={{ whiteSpace: 'nowrap', background: activeTab === 'sources' ? 'var(--primary)' : 'transparent', color: activeTab === 'sources' ? 'white' : 'var(--text-secondary)', border: 'none', boxShadow: 'none' }}
        >
          Data Sources
        </button>
      </div>

      {activeTab === 'detection' && (
        <div className="card" style={{ maxWidth: '800px' }}>
          <h3 style={{ marginTop: 0 }}>Alert Suppression Rules</h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', marginBottom: '1.5rem' }}>
            Alerts matching these rules will be quietly scored but will NOT generate a SIEM payload, Slack notification, or show up in the Triage Inbox.
          </p>

          <form onSubmit={addRule} style={{ display: 'flex', gap: '1rem', marginBottom: '2rem' }}>
            <select 
              className="form-control" 
              value={ruleType} 
              onChange={e => setRuleType(e.target.value)}
              style={{ padding: '0.5rem', borderRadius: '0.25rem', border: '1px solid var(--border-color)', background: 'var(--bg-color)', color: 'var(--text-primary)' }}
            >
              <option value="identity">Identity / User</option>
              <option value="ip">Source IP</option>
              <option value="cloud">Cloud Provider</option>
            </select>
            
            <input 
              type="text" 
              placeholder={`Enter ${ruleType} to suppress...`}
              value={ruleValue}
              onChange={e => setRuleValue(e.target.value)}
              style={{ flex: 1, padding: '0.5rem', borderRadius: '0.25rem', border: '1px solid var(--border-color)', background: 'var(--bg-color)', color: 'var(--text-primary)' }}
            />
            
            <button type="submit" className="btn btn-primary" disabled={loading || !ruleValue.trim()}>
              Add Rule
            </button>
          </form>

          <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '2px solid var(--border-color)' }}>
                <th style={{ padding: '0.75rem 0' }}>Type</th>
                <th style={{ padding: '0.75rem 0' }}>Value</th>
                <th style={{ padding: '0.75rem 0' }}>Created At</th>
                <th style={{ padding: '0.75rem 0', textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rules.length === 0 ? (
                <tr>
                  <td colSpan="4" style={{ padding: '2rem 0', textAlign: 'center', color: 'var(--text-secondary)' }}>
                    No suppression rules active.
                  </td>
                </tr>
              ) : (
                rules.map(rule => (
                  <tr key={rule.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                    <td style={{ padding: '0.75rem 0', textTransform: 'capitalize' }}>{rule.rule_type}</td>
                    <td style={{ padding: '0.75rem 0', fontWeight: 500 }}>{rule.value}</td>
                    <td style={{ padding: '0.75rem 0', color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                      {new Date(rule.created_at).toLocaleString()}
                    </td>
                    <td style={{ padding: '0.75rem 0', textAlign: 'right' }}>
                      <button 
                        onClick={() => deleteRule(rule.id)}
                        className="btn btn-secondary" 
                        style={{ padding: '0.25rem 0.75rem', fontSize: '0.75rem', color: 'var(--danger)', borderColor: 'var(--danger-bg)' }}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {activeTab === 'system' && (
        <div className="card" style={{ maxWidth: '800px' }}>
          <h3 style={{ marginTop: 0 }}>System Integrations</h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', marginBottom: '1.5rem' }}>
            Configure downstream systems for automated response.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1rem', background: 'var(--bg-primary)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
              <div>
                <strong style={{ display: 'block', marginBottom: '0.25rem' }}>ServiceNow ITSM</strong>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Automatically create incident tickets for confirmed quantum anomalies.</span>
              </div>
              <button className="btn btn-secondary" disabled>Configured (Mock)</button>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'security' && (
        <div className="card" style={{ maxWidth: '800px' }}>
          <h3 style={{ marginTop: 0 }}>Security & MFA</h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', marginBottom: '2rem' }}>
            Configure Multi-Factor Authentication for your admin account.
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
            <div style={{ padding: '1.5rem', background: 'var(--bg-primary)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
                <div>
                  <h4 style={{ margin: '0 0 0.5rem 0' }}>Authenticator App (TOTP)</h4>
                  <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Use an app like Google Authenticator or Authy to generate a 6-digit code.</p>
                </div>
                <div>
                  {mfaStatus.totp_enabled ? (
                    <span style={{ color: 'var(--success)', fontWeight: 'bold', fontSize: '0.85rem' }}>Enabled</span>
                  ) : (
                    <span style={{ color: 'var(--warning)', fontWeight: 'bold', fontSize: '0.85rem' }}>Not Enabled</span>
                  )}
                </div>
              </div>
              
              {!mfaStatus.totp_enabled && !qrCode && (
                <button className="btn btn-secondary" onClick={setupTotp} disabled={loading}>
                  Setup Authenticator
                </button>
              )}

              {qrCode && (
                <div style={{ display: 'flex', gap: '2rem', alignItems: 'center', marginTop: '1rem', padding: '1rem', background: 'white', borderRadius: '8px' }}>
                  <img src={`data:image/png;base64,${qrCode}`} alt="QR Code" style={{ width: '150px', height: '150px' }} />
                  <form onSubmit={verifyTotp} style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                    <p style={{ color: 'black', margin: 0, fontSize: '0.9rem' }}>Scan the QR code and enter the 6-digit code to verify:</p>
                    <input 
                      type="text" 
                      value={totpCode}
                      onChange={e => setTotpCode(e.target.value)}
                      placeholder="000000"
                      maxLength={6}
                      style={{ padding: '0.5rem', fontSize: '1.2rem', letterSpacing: '0.25em', textAlign: 'center', borderRadius: '4px', border: '1px solid #ccc', color: 'black' }}
                    />
                    <button type="submit" className="btn btn-primary" disabled={loading || totpCode.length !== 6}>Verify & Enable</button>
                  </form>
                </div>
              )}
            </div>

            <div style={{ padding: '1.5rem', background: 'var(--bg-primary)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
                <div>
                  <h4 style={{ margin: '0 0 0.5rem 0' }}>Hardware Security Keys (WebAuthn)</h4>
                  <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Use a YubiKey, TouchID, or Windows Hello for frictionless security.</p>
                </div>
                <div>
                  {mfaStatus.webauthn_enabled ? (
                    <span style={{ color: 'var(--success)', fontWeight: 'bold', fontSize: '0.85rem' }}>Enabled</span>
                  ) : (
                    <span style={{ color: 'var(--text-secondary)', fontWeight: 'bold', fontSize: '0.85rem' }}>Not Configured</span>
                  )}
                </div>
              </div>
              
              <button className="btn btn-primary" onClick={registerHardwareKey} disabled={loading}>
                Register New Hardware Key
              </button>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'playbooks' && (
        <div className="card" style={{ maxWidth: '900px' }}>
          <h3 style={{ marginTop: 0 }}>SOAR Playbooks</h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', marginBottom: '1.5rem' }}>Automated response rules that execute immediately when a new alert meets the conditions.</p>
          
          <form onSubmit={addPlaybook} style={{ display: 'flex', gap: '0.5rem', marginBottom: '2rem', alignItems: 'center' }}>
            <span style={{ color: 'var(--text-secondary)' }}>IF</span>
            <select className="form-control" value={pbField} onChange={e => setPbField(e.target.value)} style={{ padding: '0.5rem', borderRadius: '0.25rem', border: '1px solid var(--border-color)', background: 'var(--bg-color)', color: 'var(--text-primary)' }}>
              <option value="score">Ensemble Score</option>
              <option value="attack_phase">Attack Phase</option>
              <option value="cloud">Cloud Provider</option>
            </select>
            <select className="form-control" value={pbOp} onChange={e => setPbOp(e.target.value)} style={{ padding: '0.5rem', borderRadius: '0.25rem', border: '1px solid var(--border-color)', background: 'var(--bg-color)', color: 'var(--text-primary)' }}>
              <option value=">">&gt;</option>
              <option value="<">&lt;</option>
              <option value="==">==</option>
            </select>
            <input type="text" value={pbVal} onChange={e => setPbVal(e.target.value)} placeholder="e.g. 0.85 or Exfiltration" style={{ padding: '0.5rem', borderRadius: '0.25rem', border: '1px solid var(--border-color)', background: 'var(--bg-color)', color: 'var(--text-primary)' }} required />
            
            <span style={{ color: 'var(--text-secondary)', marginLeft: '0.5rem' }}>THEN</span>
            <select className="form-control" value={pbAction} onChange={e => setPbAction(e.target.value)} style={{ padding: '0.5rem', borderRadius: '0.25rem', border: '1px solid var(--border-color)', background: 'var(--bg-color)', color: 'var(--text-primary)' }}>
              <option value="auto_isolate">Auto-Isolate Identity</option>
              <option value="create_ticket">Create ITSM Ticket</option>
            </select>
            
            <button type="submit" className="btn btn-primary" disabled={loading} style={{ marginLeft: '1rem' }}>Create</button>
          </form>

          <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '2px solid var(--border-color)' }}>
                <th style={{ padding: '0.75rem 0' }}>Condition</th>
                <th style={{ padding: '0.75rem 0' }}>Action</th>
                <th style={{ padding: '0.75rem 0' }}>Created At</th>
                <th style={{ padding: '0.75rem 0', textAlign: 'right' }}>Controls</th>
              </tr>
            </thead>
            <tbody>
              {playbooks.map(pb => (
                <tr key={pb.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                  <td style={{ padding: '0.75rem 0' }}><span style={{ color: 'var(--primary)', fontFamily: 'monospace' }}>{pb.condition_field} {pb.condition_operator} {pb.condition_value}</span></td>
                  <td style={{ padding: '0.75rem 0', fontWeight: 'bold' }}>{pb.action === 'auto_isolate' ? 'Isolate Identity' : 'Create Ticket'}</td>
                  <td style={{ padding: '0.75rem 0', color: 'var(--text-secondary)', fontSize: '0.875rem' }}>{new Date(pb.created_at).toLocaleString()}</td>
                  <td style={{ padding: '0.75rem 0', textAlign: 'right' }}>
                    <button onClick={() => deletePlaybook(pb.id)} className="btn btn-secondary" style={{ padding: '0.25rem 0.75rem', fontSize: '0.75rem', color: 'var(--danger)', borderColor: 'var(--danger-bg)' }}>Delete</button>
                  </td>
                </tr>
              ))}
              {playbooks.length === 0 && (
                <tr><td colSpan="4" style={{ padding: '2rem 0', textAlign: 'center', color: 'var(--text-secondary)' }}>No playbooks configured.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      
      {activeTab === 'audit' && (
        <div className="card" style={{ maxWidth: '800px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
            <h3 style={{ margin: 0 }}>Analyst Audit Logs</h3>
            <button className="btn btn-secondary" onClick={fetchAuditLogs} style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}>Refresh</button>
          </div>
          
          <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '2px solid var(--border-color)' }}>
                <th style={{ padding: '0.75rem 0' }}>Timestamp</th>
                <th style={{ padding: '0.75rem 0' }}>User</th>
                <th style={{ padding: '0.75rem 0' }}>Action</th>
                <th style={{ padding: '0.75rem 0' }}>Target</th>
              </tr>
            </thead>
            <tbody>
              {auditLogs.map(log => (
                <tr key={log.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                  <td style={{ padding: '0.75rem 0', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>{new Date(log.timestamp).toLocaleString()}</td>
                  <td style={{ padding: '0.75rem 0', fontWeight: 'bold' }}>{log.username}</td>
                  <td style={{ padding: '0.75rem 0' }}>{log.action}</td>
                  <td style={{ padding: '0.75rem 0', fontFamily: 'monospace', fontSize: '0.85rem' }}>{log.target}</td>
                </tr>
              ))}
              {auditLogs.length === 0 && (
                <tr><td colSpan="4" style={{ padding: '2rem 0', textAlign: 'center', color: 'var(--text-secondary)' }}>No audit logs found.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {activeTab === 'sources' && (
        <div className="card" style={{ maxWidth: '800px' }}>
          <h3 style={{ marginTop: 0 }}>SIEM Ingestion Webhook</h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', marginBottom: '1.5rem' }}>
            Forward raw JSON, AWS CloudTrail, or GCP Audit logs directly into the Quantum simulation engine.
          </p>
          <div style={{ background: '#1e293b', padding: '1rem', borderRadius: '8px', color: '#e2e8f0', fontFamily: 'monospace', fontSize: '0.85rem', marginBottom: '1rem' }}>
            POST /api/ingest/webhook
          </div>
          <p style={{ fontSize: '0.85rem' }}>Example payload:</p>
          <pre style={{ background: '#1e293b', padding: '1rem', borderRadius: '8px', color: '#e2e8f0', fontSize: '0.8rem', overflowX: 'auto' }}>
{`{
  "cloud": "AWS",
  "src_ip": "203.0.113.5",
  "user": "admin@corp.com",
  "action": "s3:GetObject",
  "bytes_out": 2147483648
}`}
          </pre>
          <p style={{ fontSize: '0.85rem', color: '#ef4444' }}>
            Note: The Automated Exfiltration (DLP-Lite) engine automatically flags any event with >1GB of bytes_out as CRITICAL.
          </p>
        </div>
      )}

      {activeTab === 'tenants' && role === 'SUPER_ADMIN' && (
        <div className="card" style={{ maxWidth: '800px' }}>
          <h3 style={{ marginTop: 0 }}>Tenant Management</h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', marginBottom: '1.5rem' }}>
            Provision isolated tenants for MSSP customers.
          </p>
          <form onSubmit={createTenant} style={{ display: 'flex', gap: '1rem', marginBottom: '2rem' }}>
            <input type="text" className="form-control" placeholder="Tenant Name" value={newTenantName} onChange={e => setNewTenantName(e.target.value)} required />
            <button type="submit" className="btn btn-primary" disabled={loading}>Create Tenant</button>
          </form>
          <table className="table" style={{ width: '100%', textAlign: 'left' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-color)' }}>
                <th>ID</th><th>Name</th><th>Compliance Mode</th><th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {tenants.map(t => (
                <tr key={t.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                  <td style={{ padding: '1rem 0' }}>{t.id}</td>
                  <td>{t.name}</td>
                  <td>
                    <span style={{ color: t.compliance_mode_enabled ? '#10b981' : '#f59e0b', fontWeight: 'bold' }}>
                      {t.compliance_mode_enabled ? 'Enforced' : 'Disabled'}
                    </span>
                  </td>
                  <td>
                    <button className="btn btn-secondary" onClick={() => toggleCompliance(t.id)}>Toggle Compliance</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {activeTab === 'users' && (role === 'SUPER_ADMIN' || role === 'TENANT_ADMIN') && (
        <div className="card" style={{ maxWidth: '800px' }}>
          <h3 style={{ marginTop: 0 }}>User Access</h3>
          <form onSubmit={createUser} style={{ display: 'flex', gap: '1rem', marginBottom: '2rem', flexWrap: 'wrap' }}>
            <input type="text" className="form-control" placeholder="Username" value={newUsername} onChange={e => setNewUsername(e.target.value)} required />
            <input type="password" className="form-control" placeholder="Password" value={newPassword} onChange={e => setNewPassword(e.target.value)} required />
            <select className="form-control" value={newUserRole} onChange={e => setNewUserRole(e.target.value)}>
              <option value="TIER_1">Tier 1 Analyst</option>
              <option value="TIER_2">Tier 2 Analyst</option>
              <option value="READ_ONLY">Read Only</option>
              {role === 'SUPER_ADMIN' && <option value="TENANT_ADMIN">Tenant Admin</option>}
            </select>
            {role === 'SUPER_ADMIN' && (
              <select className="form-control" value={newUserTenant} onChange={e => setNewUserTenant(e.target.value)} required>
                <option value="">Select Tenant...</option>
                {tenants.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            )}
            <button type="submit" className="btn btn-primary" disabled={loading}>Create User</button>
          </form>
          <table className="table" style={{ width: '100%', textAlign: 'left' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-color)' }}>
                <th>ID</th><th>Username</th><th>Role</th><th>Tenant ID</th>
              </tr>
            </thead>
            <tbody>
              {users.map(u => (
                <tr key={u.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                  <td style={{ padding: '1rem 0' }}>{u.id}</td>
                  <td>{u.username}</td>
                  <td>{u.role}</td>
                  <td>{u.tenant_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default Settings;

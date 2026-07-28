import React, { useState, useEffect, useCallback } from 'react';
import toast from 'react-hot-toast';
import { MIN_PASSWORD_LENGTH, ROLE_LABELS, assignableRoles } from '../roles';

function Settings({ token }) {
  const [rules, setRules] = useState([]);
  const [ruleType, setRuleType] = useState('identity');
  const [ruleValue, setRuleValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('detection');

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
  const currentUsername = localStorage.getItem('quantum_username');
  const [tenants, setTenants] = useState([]);
  const [users, setUsers] = useState([]);
  const [usersLoaded, setUsersLoaded] = useState(false);
  const [newTenantName, setNewTenantName] = useState('');
  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newUserRole, setNewUserRole] = useState('TIER_1');
  const [newUserTenant, setNewUserTenant] = useState('');
  const [userAction, setUserAction] = useState(null); // { id, kind: 'password' | 'delete' }
  const [userActionPassword, setUserActionPassword] = useState('');
  const [busyUserId, setBusyUserId] = useState(null);

  const fetchTenants = useCallback(async () => {
    try {
      const res = await fetch('/api/tenants', { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) setTenants(await res.json());
    } catch (e) { console.error(e); }
  }, [token]);
  
  const fetchUsers = useCallback(async () => {
    try {
      const res = await fetch('/api/users', { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) {
        const data = await res.json();
        setUsers(Array.isArray(data) ? data : []);
      } else {
        toast.error('Could not load the user directory');
      }
    } catch (e) {
      console.error(e);
      toast.error('Could not load the user directory');
    } finally {
      setUsersLoaded(true);
    }
  }, [token]);
  
  useEffect(() => {
    if (role === 'SUPER_ADMIN') fetchTenants();
    if (role === 'SUPER_ADMIN' || role === 'TENANT_ADMIN') fetchUsers();
  }, [role, fetchTenants, fetchUsers]);

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
      } else {
        const data = await res.json().catch(() => ({}));
        toast.error(data.message || 'Failed to create tenant');
      }
    } catch { toast.error("Failed to create tenant"); }
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
      } else {
        const data = await res.json().catch(() => ({}));
        toast.error(data.message || 'Failed to update compliance');
      }
    } catch { toast.error("Failed to update compliance"); }
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
      } else {
        const data = await res.json().catch(() => ({}));
        toast.error(data.message || 'Failed to create user');
      }
    } catch { toast.error("Failed to create user"); }
  };

  const closeUserAction = () => {
    setUserAction(null);
    setUserActionPassword('');
  };

  const mutateUser = async (user, { path = '', method = 'PATCH', body, success, failure }) => {
    setBusyUserId(user.id);
    try {
      const res = await fetch(`/api/users/${user.id}${path}`, {
        method,
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: body ? JSON.stringify(body) : undefined,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        toast.error(data.message || failure);
        return false;
      }
      toast.success(data.message || success);
      closeUserAction();
      fetchUsers();
      return true;
    } catch {
      toast.error(failure);
      return false;
    } finally {
      setBusyUserId(null);
    }
  };

  const changeUserRole = (user, nextRole) => mutateUser(user, {
    body: { role: nextRole },
    success: `${user.username} is now ${ROLE_LABELS[nextRole] || nextRole}`,
    failure: 'Failed to change role',
  });

  const changeUserTenant = (user, tenantId) => mutateUser(user, {
    body: { tenant_id: Number(tenantId) },
    success: `${user.username} moved to another tenant`,
    failure: 'Failed to move user',
  });

  const toggleUserActive = (user) => mutateUser(user, {
    body: { is_active: !user.is_active },
    success: user.is_active ? `${user.username} deactivated` : `${user.username} reactivated`,
    failure: 'Failed to update account status',
  });

  const resetUserMfa = (user) => mutateUser(user, {
    path: '/mfa',
    method: 'DELETE',
    success: `MFA cleared for ${user.username}`,
    failure: 'Failed to clear MFA enrollment',
  });

  const deleteUser = (user) => mutateUser(user, {
    method: 'DELETE',
    success: `${user.username} deleted`,
    failure: 'Failed to delete user',
  });

  const submitUserPassword = (e, user) => {
    e.preventDefault();
    return mutateUser(user, {
      path: '/password',
      method: 'POST',
      body: { password: userActionPassword },
      success: `Password reset for ${user.username}`,
      failure: 'Failed to reset password',
    });
  };

  const fetchPlaybooks = useCallback(async () => {
    try {
      const res = await fetch('/api/playbooks', { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) setPlaybooks(await res.json());
    } catch (e) { console.error(e); }
  }, [token]);

  const fetchAuditLogs = useCallback(async () => {
    try {
      const res = await fetch('/api/audit', { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) setAuditLogs(await res.json());
    } catch (e) { console.error(e); }
  }, [token]);

  const fetchRules = useCallback(async () => {
    try {
      const res = await fetch('/api/rules', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      if (!res.ok || !Array.isArray(data)) {
        throw new Error(data?.message || 'Failed to load suppression rules');
      }
      setRules(data);
    } catch (e) {
      console.error(e);
      toast.error('Failed to load suppression rules');
    }
  }, [token]);

  useEffect(() => {
    fetchRules();
    fetchPlaybooks();
    fetchAuditLogs();
  }, [fetchAuditLogs, fetchPlaybooks, fetchRules]);

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
    } catch {
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
    } catch {
      toast.error('Failed to remove playbook');
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Administration</h1>
        <p className="page-subtitle">Manage detection policy, response automation, access, and integrations.</p>
      </div>

      <div className="settings-tabs" role="tablist" aria-label="Administration sections">
        <button 
          className={`btn ${activeTab === 'detection' ? 'is-active' : ''}`}
          onClick={() => setActiveTab('detection')}
          role="tab"
          aria-selected={activeTab === 'detection'}
        >
          Suppression
        </button>
        <button 
          className={`btn ${activeTab === 'playbooks' ? 'is-active' : ''}`}
          onClick={() => setActiveTab('playbooks')}
          role="tab"
          aria-selected={activeTab === 'playbooks'}
        >
          Playbooks
        </button>
        <button 
          className={`btn ${activeTab === 'audit' ? 'is-active' : ''}`}
          onClick={() => setActiveTab('audit')}
          role="tab"
          aria-selected={activeTab === 'audit'}
        >
          Audit
        </button>
        <button 
          className={`btn ${activeTab === 'system' ? 'is-active' : ''}`}
          onClick={() => setActiveTab('system')}
          role="tab"
          aria-selected={activeTab === 'system'}
        >
          Integrations
        </button>

        {role === 'SUPER_ADMIN' && (
          <button 
            className={`btn ${activeTab === 'tenants' ? 'is-active' : ''}`}
            onClick={() => setActiveTab('tenants')}
            role="tab"
            aria-selected={activeTab === 'tenants'}
          >
            Tenants
          </button>
        )}
        {(role === 'SUPER_ADMIN' || role === 'TENANT_ADMIN') && (
          <button 
            className={`btn ${activeTab === 'users' ? 'is-active' : ''}`}
            onClick={() => setActiveTab('users')}
            role="tab"
            aria-selected={activeTab === 'users'}
          >
            Users
          </button>
        )}
        <button 
          className={`btn ${activeTab === 'sources' ? 'is-active' : ''}`}
          onClick={() => setActiveTab('sources')}
          role="tab"
          aria-selected={activeTab === 'sources'}
        >
          Sources
        </button>
      </div>

      {activeTab === 'detection' && (
        <div className="card" style={{ maxWidth: '800px' }}>
          <h3 style={{ marginTop: 0 }}>Suppression rules</h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', marginBottom: '1.5rem' }}>
            Matching events remain scored for analysis but do not create analyst alerts or outbound notifications.
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
          <h3 style={{ marginTop: 0 }}>Integrations</h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', marginBottom: '1.5rem' }}>
            Configure downstream systems for automated response.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1rem', background: 'var(--bg-primary)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
              <div>
                <strong style={{ display: 'block', marginBottom: '0.25rem' }}>ServiceNow ITSM</strong>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Local adapter used by the demonstration environment.</span>
              </div>
              <span className="status-pill">Local adapter</span>
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
              <option value="ensemble">Ensemble</option>
              <option value="quantum_kernel">Quantum kernel</option>
              <option value="classical_svm">Classical SVM</option>
              <option value="isolation_forest">Isolation Forest</option>
              <option value="severity">Severity</option>
              <option value="attack_phase">Attack Phase</option>
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
            Note: The Automated Exfiltration (DLP-Lite) engine automatically flags any event with &gt;1GB of bytes_out as CRITICAL.
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
        <div className="card" style={{ maxWidth: '1100px' }}>
          <h3 style={{ marginTop: 0 }}>User accounts</h3>
          <p className="settings-hint" style={{ marginBottom: '1.5rem' }}>
            Create accounts, change roles, reset credentials, and revoke access. Deactivating an account blocks it
            immediately, including any session that is already signed in.
          </p>

          <form onSubmit={createUser} className="user-create-form">
            <div className="user-create-field">
              <label className="control-label" htmlFor="new-username">Username</label>
              <input
                id="new-username"
                type="text"
                className="form-control"
                autoComplete="off"
                value={newUsername}
                onChange={e => setNewUsername(e.target.value)}
                required
              />
            </div>
            <div className="user-create-field">
              <label className="control-label" htmlFor="new-user-password">Initial password</label>
              <input
                id="new-user-password"
                type="password"
                className="form-control"
                autoComplete="new-password"
                minLength={MIN_PASSWORD_LENGTH}
                value={newPassword}
                onChange={e => setNewPassword(e.target.value)}
                required
              />
            </div>
            <div className="user-create-field">
              <label className="control-label" htmlFor="new-user-role">Role</label>
              <select id="new-user-role" className="form-control" value={newUserRole} onChange={e => setNewUserRole(e.target.value)}>
                {assignableRoles(role).map(r => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
              </select>
            </div>
            {role === 'SUPER_ADMIN' && (
              <div className="user-create-field">
                <label className="control-label" htmlFor="new-user-tenant">Tenant</label>
                <select id="new-user-tenant" className="form-control" value={newUserTenant} onChange={e => setNewUserTenant(e.target.value)} required>
                  <option value="">Select tenant...</option>
                  {tenants.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
              </div>
            )}
            <button type="submit" className="btn btn-primary" disabled={loading}>Create user</button>
            <span className="settings-hint">Passwords must be at least {MIN_PASSWORD_LENGTH} characters.</span>
          </form>

          <div className="table-wrap">
            <table className="user-table">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Role</th>
                  {role === 'SUPER_ADMIN' && <th>Tenant</th>}
                  <th>MFA</th>
                  <th>Status</th>
                  <th>Last sign-in</th>
                  <th className="align-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.length === 0 ? (
                  <tr>
                    <td colSpan={role === 'SUPER_ADMIN' ? 7 : 6} className="user-table-empty">
                      {usersLoaded ? 'No users yet.' : 'Loading users...'}
                    </td>
                  </tr>
                ) : users.map(u => {
                  const isSelf = u.username === currentUsername;
                  const busy = busyUserId === u.id;
                  return (
                    <React.Fragment key={u.id}>
                      <tr className={u.is_active ? undefined : 'is-inactive'}>
                        <td>
                          <span className="user-name">{u.username}</span>
                          {isSelf && <span className="status-pill" style={{ marginLeft: '0.5rem' }}>You</span>}
                        </td>
                        <td>
                          {u.manageable ? (
                            <select
                              className="form-control user-role-select"
                              value={u.role}
                              disabled={busy}
                              aria-label={`Role for ${u.username}`}
                              onChange={e => changeUserRole(u, e.target.value)}
                            >
                              {assignableRoles(role).map(r => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
                            </select>
                          ) : (
                            <span>{ROLE_LABELS[u.role] || u.role}</span>
                          )}
                        </td>
                        {role === 'SUPER_ADMIN' && (
                          <td>
                            {u.manageable ? (
                              <select
                                className="form-control user-role-select"
                                value={u.tenant_id}
                                disabled={busy}
                                aria-label={`Tenant for ${u.username}`}
                                onChange={e => changeUserTenant(u, e.target.value)}
                              >
                                {tenants.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                              </select>
                            ) : (
                              <span>{tenants.find(t => t.id === u.tenant_id)?.name || `Tenant ${u.tenant_id}`}</span>
                            )}
                          </td>
                        )}
                        <td>
                          {u.mfa_enabled
                            ? <span className="status-pill is-success">Enrolled</span>
                            : <span className="settings-hint">Not enrolled</span>}
                        </td>
                        <td>
                          <span className={`status-pill ${u.is_active ? 'is-success' : 'is-danger'}`}>
                            {u.is_active ? 'Active' : 'Disabled'}
                          </span>
                        </td>
                        <td className="settings-hint">
                          {u.last_login_at ? new Date(u.last_login_at).toLocaleString() : 'Never'}
                        </td>
                        <td>
                          {u.manageable ? (
                            <div className="user-actions">
                              <button
                                type="button"
                                className="btn btn-secondary btn-compact"
                                disabled={busy}
                                onClick={() => {
                                  setUserActionPassword('');
                                  setUserAction(prev => (prev?.id === u.id && prev.kind === 'password' ? null : { id: u.id, kind: 'password' }));
                                }}
                              >
                                Reset password
                              </button>
                              {u.mfa_enabled && (
                                <button type="button" className="btn btn-secondary btn-compact" disabled={busy} onClick={() => resetUserMfa(u)}>
                                  Clear MFA
                                </button>
                              )}
                              <button type="button" className="btn btn-secondary btn-compact" disabled={busy} onClick={() => toggleUserActive(u)}>
                                {u.is_active ? 'Deactivate' : 'Activate'}
                              </button>
                              <button
                                type="button"
                                className="btn btn-danger btn-compact"
                                disabled={busy}
                                onClick={() => setUserAction(prev => (prev?.id === u.id && prev.kind === 'delete' ? null : { id: u.id, kind: 'delete' }))}
                              >
                                Delete
                              </button>
                            </div>
                          ) : (
                            <span className="settings-hint">
                              {isSelf ? 'Manage your own credentials under My account' : 'Super admin only'}
                            </span>
                          )}
                        </td>
                      </tr>
                      {userAction?.id === u.id && (
                        <tr className="user-action-row">
                          <td colSpan={role === 'SUPER_ADMIN' ? 7 : 6}>
                            {userAction.kind === 'password' ? (
                              <form className="user-action-form" onSubmit={e => submitUserPassword(e, u)}>
                                <label className="control-label" htmlFor={`reset-${u.id}`}>
                                  New password for {u.username}
                                </label>
                                <input
                                  id={`reset-${u.id}`}
                                  type="password"
                                  className="form-control"
                                  autoComplete="new-password"
                                  autoFocus
                                  minLength={MIN_PASSWORD_LENGTH}
                                  value={userActionPassword}
                                  onChange={e => setUserActionPassword(e.target.value)}
                                  required
                                />
                                <button type="submit" className="btn btn-primary btn-compact" disabled={busy}>Set password</button>
                                <button type="button" className="btn btn-secondary btn-compact" onClick={closeUserAction}>Cancel</button>
                                <span className="settings-hint">The user is not notified — share it over a trusted channel.</span>
                              </form>
                            ) : (
                              <div className="user-action-form">
                                <span>
                                  Delete <strong>{u.username}</strong> permanently? Their case assignments are cleared and
                                  past comments remain in the case history. Deactivate instead to keep the account recoverable.
                                </span>
                                <button type="button" className="btn btn-danger btn-compact" disabled={busy} onClick={() => deleteUser(u)}>
                                  Delete account
                                </button>
                                <button type="button" className="btn btn-secondary btn-compact" onClick={closeUserAction}>Cancel</button>
                              </div>
                            )}
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

export default Settings;

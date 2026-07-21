import React, { useState, useEffect } from 'react';
import toast from 'react-hot-toast';

function Settings({ token }) {
  const [rules, setRules] = useState([]);
  const [ruleType, setRuleType] = useState('identity');
  const [ruleValue, setRuleValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('detection');

  useEffect(() => {
    fetchRules();
  }, []);

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

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Settings & Rules</h1>
        <p className="page-subtitle">Manage system configuration and alert suppression rules.</p>
      </div>

      <div style={{ display: 'flex', gap: '1rem', marginBottom: '2rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem' }}>
        <button 
          className={`btn ${activeTab === 'detection' ? 'btn-primary' : ''}`}
          onClick={() => setActiveTab('detection')}
          style={{ background: activeTab === 'detection' ? 'var(--primary)' : 'transparent', color: activeTab === 'detection' ? 'white' : 'var(--text-secondary)', border: 'none', boxShadow: 'none' }}
        >
          Detection Engineering (Rules)
        </button>
        <button 
          className={`btn ${activeTab === 'system' ? 'btn-primary' : ''}`}
          onClick={() => setActiveTab('system')}
          style={{ background: activeTab === 'system' ? 'var(--primary)' : 'transparent', color: activeTab === 'system' ? 'white' : 'var(--text-secondary)', border: 'none', boxShadow: 'none' }}
        >
          System Configuration
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
    </div>
  );
}

export default Settings;

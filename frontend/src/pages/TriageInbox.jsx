import React, { useState, useEffect, useRef } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Search, Download, Briefcase } from 'lucide-react';
import toast from 'react-hot-toast';
import InfoBubble from '../components/InfoBubble';
import EventDrillDownModal from '../components/EventDrillDownModal';
import IntrusionExplanation from '../components/IntrusionExplanation';
import { apiFetch } from '../api';
import { canMutateAlerts } from '../roles';

const ScoreBar = ({ label, score, threshold }) => {
  const percentage = Math.min(Math.max(score * 100, 0), 100);
  let color = 'var(--success)';
  if (score >= threshold) color = 'var(--danger)';
  else if (score >= threshold * 0.7) color = '#f59e0b';

  return (
    <div style={{ marginBottom: '1rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.875rem', marginBottom: '0.35rem' }}>
        <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{label}</span>
        <span style={{ color: 'var(--text-secondary)' }}>{score.toFixed(2)}</span>
      </div>
      <div style={{ height: '6px', width: '100%', background: 'var(--border-color)', borderRadius: '3px', overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${percentage}%`, background: color, transition: 'width 0.5s ease-out' }}></div>
      </div>
    </div>
  );
};

function TriageInbox({ state, token }) {
  const role = localStorage.getItem('quantum_role');
  const canMutate = canMutateAlerts(role);
  const isMspAdmin = role === 'SUPER_ADMIN';
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const alertIdParam = searchParams.get('alertId');

  const [alerts, setAlerts] = useState([]);
  const [selectedAlert, setSelectedAlert] = useState(null);
  const [modalAlert, setModalAlert] = useState(null);
  const [filter, setFilter] = useState('open');
  const [assigneeFilter, setAssigneeFilter] = useState('');
  const [tenantFilter, setTenantFilter] = useState('');
  const [tenants, setTenants] = useState([]);
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [cases, setCases] = useState([]);
  const [linkCaseId, setLinkCaseId] = useState('');
  const searchTimer = useRef(null);

  const appendTenantScope = (params) => {
    if (!isMspAdmin) return params;
    params.append('scope', 'all');
    if (tenantFilter) params.append('tenant_id', tenantFilter);
    return params;
  };

  useEffect(() => {
    clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => {
      setSearch(searchInput);
      setPage(1);
    }, 300);
    return () => clearTimeout(searchTimer.current);
  }, [searchInput]);

  useEffect(() => {
    if (!isMspAdmin || !token) return undefined;
    const controller = new AbortController();
    apiFetch('/api/tenants', { token, signal: controller.signal })
      .then((data) => setTenants(Array.isArray(data) ? data : []))
      .catch(() => {});
    return () => controller.abort();
  }, [isMspAdmin, token]);

  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      try {
        const params = appendTenantScope(new URLSearchParams({
          page, limit: 10, status: filter, search
        }));
        if (assigneeFilter) params.append('assignee', assigneeFilter);
        if (startDate) params.append('start_date', startDate + "T00:00:00Z");
        if (endDate) params.append('end_date', endDate + "T23:59:59Z");

        const data = await apiFetch(`/api/alerts?${params.toString()}`, {
          token,
          signal: controller.signal,
        });
        setAlerts(data.alerts || []);
        setTotalPages(data.pages || 1);

        setSelectedAlert(prev => {
          if (alertIdParam) return prev;
          if (prev) {
            const refreshed = (data.alerts || []).find(a => a.id === prev.id);
            return refreshed || prev;
          }
          return (data.alerts && data.alerts[0]) || null;
        });
      } catch (e) {
        if (e.name !== 'AbortError') console.error(e);
      }
    };
    load();
    return () => controller.abort();
  }, [filter, assigneeFilter, page, search, startDate, endDate, state.open_alerts, token, alertIdParam, isMspAdmin, tenantFilter]);

  useEffect(() => {
    if (!alertIdParam || !token) return undefined;
    const controller = new AbortController();
    const qs = isMspAdmin ? '?scope=all' : '';
    apiFetch(`/api/alert/${alertIdParam}${qs}`, { token, signal: controller.signal })
      .then(data => {
        if (!data.message) {
          setSelectedAlert(data);
          setModalAlert(data);
          setFilter(data.status || 'all');
        }
      })
      .catch(e => { if (e.name !== 'AbortError') console.error(e); });
    return () => controller.abort();
  }, [alertIdParam, token, isMspAdmin]);

  useEffect(() => {
    const params = new URLSearchParams();
    appendTenantScope(params);
    const qs = params.toString() ? `?${params.toString()}` : '';
    apiFetch(`/api/cases${qs}`, { token })
      .then(setCases)
      .catch(() => {});
  }, [token, isMspAdmin, tenantFilter]);

  const fetchAlerts = async () => {
    try {
      const params = appendTenantScope(new URLSearchParams({
        page, limit: 10, status: filter, search
      }));
      if (assigneeFilter) params.append('assignee', assigneeFilter);
      if (startDate) params.append('start_date', startDate + "T00:00:00Z");
      if (endDate) params.append('end_date', endDate + "T23:59:59Z");
      const data = await apiFetch(`/api/alerts?${params.toString()}`, { token });
      setAlerts(data.alerts || []);
      setTotalPages(data.pages || 1);
    } catch (e) {
      console.error(e);
    }
  };

  const handleAction = async (alertId, action) => {
    try {
      const data = await apiFetch(`/api/alert/${alertId}/action?action=${action}`, {
        method: 'POST',
        token,
      });
      setSelectedAlert(data.alert);
      if (modalAlert?.id === alertId) setModalAlert(data.alert);
      fetchAlerts();
      if (action === 'escalate' && data.case_id) {
        toast.success(data.message || `Escalated to CASE-${String(data.case_id).padStart(4, '0')}`);
        navigate(`/cases?caseId=${data.case_id}`);
        return data;
      }
      toast.success(`Alert marked as ${action.replace('_', ' ')}`);
      return data;
    } catch (e) {
      console.error(e);
      toast.error(e.message || 'Failed to update alert');
      throw e;
    }
  };

  const handleLinkToCase = async () => {
    if (!selectedAlert || !linkCaseId) {
      toast.error('Select a case first');
      return;
    }
    try {
      await apiFetch(`/api/cases/${linkCaseId}/alerts`, {
        method: 'POST',
        token,
        json: { alert_id: selectedAlert.id },
      });
      toast.success(`Alert linked to CASE-${String(linkCaseId).padStart(4, '0')}`);
      setSelectedAlert({ ...selectedAlert, case_id: Number(linkCaseId) });
    } catch (e) {
      toast.error(e.message || 'Failed to link alert');
    }
  };

  const handleExport = async () => {
    const params = appendTenantScope(new URLSearchParams({ status: filter, search }));
    if (assigneeFilter) params.append('assignee', assigneeFilter);
    if (startDate) params.append('start_date', startDate + "T00:00:00Z");
    if (endDate) params.append('end_date', endDate + "T23:59:59Z");
    try {
      const res = await fetch(`/api/alerts/export?${params.toString()}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!res.ok) throw new Error('Export failed');
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'alerts_export.csv';
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (e) {
      console.error(e);
      toast.error('Failed to export alerts');
    }
  };

  const getSeverityColor = (score) => {
    if (score >= 0.85) return 'var(--danger)';
    if (score >= state.threshold) return '#f59e0b';
    return 'var(--success)';
  };

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 className="page-title">Triage</h1>
          <p className="page-subtitle">Review, classify, and route alerts requiring analyst attention.</p>
        </div>
        
        <div className="page-actions">
          <input 
            type="date"
            className="form-control"
            aria-label="Start date"
            value={startDate}
            onChange={e => { setStartDate(e.target.value); setPage(1); }}
          />
          <span style={{ color: 'var(--text-secondary)' }}>to</span>
          <input 
            type="date"
            className="form-control"
            aria-label="End date"
            value={endDate}
            onChange={e => { setEndDate(e.target.value); setPage(1); }}
          />
          
          <div className="search-field">
            <Search size={15} />
            <input 
              type="text" 
              placeholder="Search identity, IP, or cloud"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              aria-label="Search alerts"
            />
          </div>
          {isMspAdmin && (
            <select
              className="form-control"
              aria-label="Filter by tenant"
              value={tenantFilter}
              onChange={(e) => { setTenantFilter(e.target.value); setPage(1); }}
              style={{ maxWidth: '220px' }}
            >
              <option value="">All tenants</option>
              {tenants.map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          )}
        </div>
      </div>

      <div className="toolbar">
        <div className="segmented-control" aria-label="Alert status filter">
          {['open', 'all', 'acknowledged', 'false_positive', 'escalated'].map(f => (
            <button
              key={f}
              type="button"
              className={filter === f && !assigneeFilter ? 'is-active' : ''}
              aria-pressed={filter === f && !assigneeFilter}
              onClick={() => { setFilter(f); setAssigneeFilter(''); setPage(1); }}
            >
              {f.replace('_', ' ')}
            </button>
          ))}
          <button
            type="button"
            className={assigneeFilter === 'me' ? 'is-active' : ''}
            aria-pressed={assigneeFilter === 'me'}
            onClick={() => { setAssigneeFilter('me'); setFilter('all'); setPage(1); }}
          >
            My queue
          </button>
          <button
            type="button"
            className={assigneeFilter === 'unassigned' ? 'is-active' : ''}
            aria-pressed={assigneeFilter === 'unassigned'}
            onClick={() => { setAssigneeFilter('unassigned'); setFilter('open'); setPage(1); }}
          >
            Unassigned
          </button>
        </div>
        <button className="btn btn-secondary" onClick={handleExport}>
          <Download size={16} /> Export CSV
        </button>
      </div>

      <div className="triage-grid">
        <div className="queue-list" style={{ paddingRight: '0' }}>
          {alerts.length === 0 ? (
            <div className="empty-state" style={{ padding: '2rem 1rem' }}>
              <p>No alerts match this filter.</p>
            </div>
          ) : (
            alerts.map(alert => (
              <button
                type="button"
                key={alert.id}
                className={`alert-item ${alert.status !== 'open' ? 'acked' : ''} ${selectedAlert?.id === alert.id ? 'active' : ''}`}
                onClick={() => { setSelectedAlert(alert); setSearchParams({}); }}
              >
                <div className="alert-item-header">
                  <span>{alert.severity} • {alert.cloud}</span>
                  <span>{alert.score.toFixed(2)}</span>
                </div>
                {alert.tenant_name && (
                  <div className="tenant-chip" title={`Tenant ID ${alert.tenant_id}`}>
                    {alert.tenant_name}
                  </div>
                )}
                <div className="alert-item-body">
                  {alert.short_identity}
                </div>
                {alert.assignee_id && (
                  <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                    Assigned
                  </div>
                )}
              </button>
            ))
          )}
          
          {totalPages > 1 && (
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1rem 0.5rem', marginTop: 'auto' }}>
              <button 
                className="btn btn-secondary" 
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
                style={{ padding: '0.25rem 0.5rem' }}
              >
                <ChevronLeft size={16} /> Prev
              </button>
              <span style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>Page {page} of {totalPages}</span>
              <button 
                className="btn btn-secondary" 
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                style={{ padding: '0.25rem 0.5rem' }}
              >
                Next <ChevronRight size={16} />
              </button>
            </div>
          )}
        </div>

        <div className="detail-pane">
          {selectedAlert ? (
            <div className="detail-view">
              <div className="detail-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                  <div style={{ color: 'var(--danger)', fontSize: '0.75rem', fontWeight: 700, letterSpacing: '0.05em', marginBottom: '0.5rem', textTransform: 'uppercase' }}>
                    {selectedAlert.severity} • {selectedAlert.cloud} • {selectedAlert.status.replace('_', ' ')}
                    {selectedAlert.attack_phase ? ` • ${selectedAlert.attack_phase}` : ''}
                  </div>
                  {selectedAlert.tenant_name && (
                    <div className="tenant-chip tenant-chip--lg" style={{ marginBottom: '0.65rem' }}>
                      Tenant: {selectedAlert.tenant_name}
                    </div>
                  )}
                  <h3 className="detail-title">{selectedAlert.short_identity}</h3>
                  <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                    Full identity: {selectedAlert.identity} <br/> Source IP: {selectedAlert.source_ip}
                  </div>
                </div>
                <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', textAlign: 'right' }}>
                  {new Date(selectedAlert.timestamp).toLocaleString()}
                  <div style={{ marginTop: '0.5rem' }}>
                    <button type="button" className="btn btn-secondary" onClick={() => setModalAlert(selectedAlert)}>
                      Full investigation
                    </button>
                  </div>
                </div>
              </div>

              <IntrusionExplanation alert={selectedAlert} />

              <div className="action-box">
                <h4 style={{ display: 'flex', alignItems: 'center' }}>
                  Recommended next steps
                  <InfoBubble text="Actionable steps for analysts to investigate and remediate the threat." />
                </h4>
                <ul>
                  {(selectedAlert.actions || []).map((act, i) => <li key={i}>{act}</li>)}
                </ul>
              </div>

              {canMutate && (
                <div className="button-group">
                  {!selectedAlert.assignee_id && (
                    <button className="btn btn-secondary" onClick={() => handleAction(selectedAlert.id, 'claim')}>Claim</button>
                  )}
                  {selectedAlert.assignee_id && (
                    <button className="btn btn-secondary" onClick={() => handleAction(selectedAlert.id, 'release')}>Release</button>
                  )}
                  {selectedAlert.status === 'open' && (
                    <>
                      <button className="btn btn-primary" onClick={() => handleAction(selectedAlert.id, 'acknowledge')}>Acknowledge</button>
                      <button className="btn btn-secondary" onClick={() => handleAction(selectedAlert.id, 'false_positive')}>Mark False Positive</button>
                      <button className="btn btn-danger" onClick={() => handleAction(selectedAlert.id, 'escalate')}>Escalate to case</button>
                    </>
                  )}
                  {selectedAlert.status === 'acknowledged' && (
                    <button className="btn btn-danger" onClick={() => handleAction(selectedAlert.id, 'escalate')}>Escalate to case</button>
                  )}
                </div>
              )}

              {canMutate && <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginTop: '0.75rem', flexWrap: 'wrap' }}>
                <Briefcase size={16} color="var(--text-secondary)" />
                <select
                  className="form-control"
                  value={linkCaseId}
                  onChange={(e) => setLinkCaseId(e.target.value)}
                  aria-label="Link alert to case"
                  style={{ maxWidth: '220px' }}
                >
                  <option value="">Add to case…</option>
                  {cases.map(c => (
                    <option key={c.id} value={c.id}>CASE-{String(c.id).padStart(4, '0')}: {c.title}</option>
                  ))}
                </select>
                <button className="btn btn-secondary" onClick={handleLinkToCase} disabled={!linkCaseId}>
                  Link
                </button>
                {selectedAlert.case_id && (
                  <button
                    type="button"
                    className="link-button"
                    onClick={() => navigate(`/cases?caseId=${selectedAlert.case_id}`)}
                    style={{ fontSize: '0.8rem' }}
                  >
                    Open CASE-{String(selectedAlert.case_id).padStart(4, '0')}
                  </button>
                )}
              </div>}

              <h4 style={{ marginTop: '2rem', marginBottom: '1rem', display: 'flex', alignItems: 'center' }}>
                Detector Breakdown
                <InfoBubble text="The individual anomaly scores from the machine learning models. A score closer to 1.0 indicates higher confidence of malicious behavior." />
              </h4>
              <div style={{ background: 'var(--bg-color)', padding: '1.25rem 1.25rem 0.25rem 1.25rem', borderRadius: '0.5rem', marginBottom: '2rem', border: '1px solid var(--border-color)' }}>
                <ScoreBar label="Final Ensemble Score" score={selectedAlert.ensemble} threshold={state.threshold} />
                <ScoreBar label="Quantum Kernel Model" score={selectedAlert.quantum_kernel} threshold={state.threshold} />
                <ScoreBar label="Classical SVM" score={selectedAlert.classical_svm} threshold={state.threshold} />
                <ScoreBar label="Isolation Forest Baseline" score={selectedAlert.isolation_forest} threshold={state.threshold} />
              </div>

              {selectedAlert.disagreement && !selectedAlert.feature_contributions?.engines?.disagreement && (
                <div className="notice-warning" style={{ marginBottom: '2rem' }}>
                  <strong>Note:</strong> {selectedAlert.disagreement}
                </div>
              )}

              <details style={{ cursor: 'pointer', padding: '1rem', border: '1px solid var(--border-color)', borderRadius: '0.5rem' }}>
                <summary style={{ fontWeight: 600 }}>Technical detail (Engine Votes)</summary>
                <div style={{ height: 200, width: '100%', marginTop: '1.5rem' }}>
                  <ResponsiveContainer>
                    <BarChart
                      layout="vertical"
                      data={[
                        { name: 'Isolation Forest', score: selectedAlert.isolation_forest },
                        { name: 'Classical SVM', score: selectedAlert.classical_svm },
                        { name: 'Quantum kernel', score: selectedAlert.quantum_kernel },
                        { name: 'Ensemble', score: selectedAlert.ensemble },
                      ]}
                      margin={{ top: 5, right: 20, bottom: 5, left: 100 }}
                    >
                      <XAxis type="number" domain={[0, 1]} />
                      <YAxis dataKey="name" type="category" width={120} tick={{ fontSize: 12 }} />
                      <Tooltip />
                      <Bar dataKey="score" fill="var(--primary)" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </details>
              
              <details style={{ cursor: 'pointer', padding: '1rem', border: '1px solid var(--border-color)', borderRadius: '0.5rem', marginTop: '1rem' }}>
                <summary style={{ fontWeight: 600 }}>Raw SIEM Payload</summary>
                <pre style={{ background: '#1e293b', color: '#e2e8f0', padding: '1rem', borderRadius: '0.5rem', overflowX: 'auto', marginTop: '1rem', fontSize: '0.75rem' }}>
                  {JSON.stringify(selectedAlert.siem, null, 2)}
                </pre>
              </details>

            </div>
          ) : (
            <div className="empty-state">
              <p>Select an alert to view details.</p>
            </div>
          )}
        </div>
      </div>

      <EventDrillDownModal
        alert={modalAlert}
        onClose={() => {
          setModalAlert(null);
          if (alertIdParam) setSearchParams({});
        }}
        onAction={handleAction}
        getSeverityColor={getSeverityColor}
      />
    </div>
  );
}

export default TriageInbox;

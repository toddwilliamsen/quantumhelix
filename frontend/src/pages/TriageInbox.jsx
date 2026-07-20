import React, { useState, useEffect } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { useSearchParams } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Search, Download } from 'lucide-react';
import toast from 'react-hot-toast';
import InfoBubble from '../components/InfoBubble';

const ScoreBar = ({ label, score, threshold }) => {
  const percentage = Math.min(Math.max(score * 100, 0), 100);
  let color = 'var(--success)';
  if (score >= threshold) color = 'var(--danger)';
  else if (score >= threshold * 0.7) color = '#f59e0b'; // amber

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
  const [searchParams, setSearchParams] = useSearchParams();
  const alertIdParam = searchParams.get('alertId');

  const [alerts, setAlerts] = useState([]);
  const [selectedAlert, setSelectedAlert] = useState(null);
  const [filter, setFilter] = useState('open');
  const [search, setSearch] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  useEffect(() => {
    fetchAlerts();
  }, [filter, page, search, startDate, endDate, state.open_alerts]); // Re-fetch when global open_alerts changes (SSE)

  useEffect(() => {
    if (alertIdParam && token) {
      // Fetch specific alert to auto-select
      fetch(`/api/alert/${alertIdParam}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      .then(r => r.json())
      .then(data => {
        if (!data.message) {
          setSelectedAlert(data);
          setFilter(data.status); // Auto-switch filter to match the alert's status
        }
      });
    }
  }, [alertIdParam, token]);

  const fetchAlerts = async () => {
    try {
      const params = new URLSearchParams({
        page, limit: 10, status: filter, search
      });
      if (startDate) params.append('start_date', startDate + "T00:00:00Z");
      if (endDate) params.append('end_date', endDate + "T23:59:59Z");
      
      const res = await fetch(`/api/alerts?${params.toString()}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      setAlerts(data.alerts || []);
      setTotalPages(data.pages || 1);
      
      // If we don't have a selected alert, select the first one
      if (!selectedAlert && data.alerts && data.alerts.length > 0 && !alertIdParam) {
        setSelectedAlert(data.alerts[0]);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleAction = async (alertId, action) => {
    try {
      const res = await fetch(`/api/alert/${alertId}/action?action=${action}`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        // Update the selected alert status in view
        setSelectedAlert(data.alert);
        fetchAlerts();
        toast.success(`Alert marked as ${action.replace('_', ' ')}`);
      } else {
        toast.error('Failed to update alert');
      }
    } catch (e) {
      console.error(e);
      toast.error('An error occurred');
    }
  };

  const handleExport = () => {
    const params = new URLSearchParams({ status: filter, search });
    if (startDate) params.append('start_date', startDate + "T00:00:00Z");
    if (endDate) params.append('end_date', endDate + "T23:59:59Z");
    
    window.open(`/api/alerts/export?${params.toString()}`, '_blank');
  };

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div className="page-header" style={{ marginBottom: '1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 className="page-title">Triage Inbox</h1>
          <p className="page-subtitle">Select an alert on the left to see what happened and what to do next.</p>
        </div>
        
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <input 
            type="date"
            className="form-control"
            value={startDate}
            onChange={e => { setStartDate(e.target.value); setPage(1); }}
            style={{ padding: '0.5rem', borderRadius: '0.5rem', border: '1px solid var(--border-color)', background: 'var(--surface)', color: 'var(--text-primary)' }}
          />
          <span style={{ color: 'var(--text-secondary)' }}>to</span>
          <input 
            type="date"
            className="form-control"
            value={endDate}
            onChange={e => { setEndDate(e.target.value); setPage(1); }}
            style={{ padding: '0.5rem', borderRadius: '0.5rem', border: '1px solid var(--border-color)', background: 'var(--surface)', color: 'var(--text-primary)' }}
          />
          
          <div style={{ display: 'flex', alignItems: 'center', background: 'var(--surface)', padding: '0.5rem 1rem', borderRadius: '0.5rem', border: '1px solid var(--border-color)', width: '250px' }}>
            <Search size={16} color="var(--text-secondary)" style={{ marginRight: '0.5rem' }} />
            <input 
              type="text" 
              placeholder="Search..." 
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              style={{ border: 'none', outline: 'none', background: 'transparent', width: '100%', color: 'var(--text-primary)' }}
            />
          </div>
        </div>
      </div>

      <div style={{ marginBottom: '1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', gap: '1rem' }}>
        {['open', 'all', 'acknowledged', 'false_positive', 'escalated'].map(f => (
          <label key={f} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', textTransform: 'capitalize' }}>
            <input 
              type="radio" 
              name="filter" 
              checked={filter === f} 
              onChange={() => { setFilter(f); setPage(1); }} 
            />
            {f.replace('_', ' ')}
          </label>
        ))}
        </div>
        <button className="btn btn-secondary" onClick={handleExport} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.25rem 0.75rem' }}>
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
              <div 
                key={alert.id}
                className={`alert-item ${alert.status !== 'open' ? 'acked' : ''} ${selectedAlert?.id === alert.id ? 'active' : ''}`}
                onClick={() => { setSelectedAlert(alert); setSearchParams({}); }} // Clear search params when manually selecting
              >
                <div className="alert-item-header">
                  <span>{alert.severity} • {alert.cloud}</span>
                  <span>{alert.score.toFixed(2)}</span>
                </div>
                <div className="alert-item-body">
                  {alert.short_identity}
                </div>
              </div>
            ))
          )}
          
          {/* Pagination Controls */}
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
                  </div>
                  <h3 className="detail-title">{selectedAlert.short_identity}</h3>
                  <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                    Full identity: {selectedAlert.identity} <br/> Source IP: {selectedAlert.source_ip}
                  </div>
                </div>
                <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                  {new Date(selectedAlert.timestamp).toLocaleString()}
                </div>
              </div>

              <h4 style={{ marginTop: 0, display: 'flex', alignItems: 'center' }}>
                What happened (plain English)
                <InfoBubble text="A human-readable summary of the anomalous behavior detected." />
              </h4>
              <p style={{ lineHeight: 1.6, color: 'var(--text-primary)' }}>
                {selectedAlert.plain_english}
              </p>

              <div className="action-box">
                <h4 style={{ display: 'flex', alignItems: 'center' }}>
                  Recommended next steps
                  <InfoBubble text="Actionable steps for analysts to investigate and remediate the threat." />
                </h4>
                <ul>
                  {selectedAlert.actions.map((act, i) => <li key={i}>{act}</li>)}
                </ul>
              </div>

              {selectedAlert.status === 'open' && (
                <div className="button-group">
                  <button className="btn btn-primary" onClick={() => handleAction(selectedAlert.id, 'acknowledge')}>Acknowledge</button>
                  <button className="btn btn-secondary" onClick={() => handleAction(selectedAlert.id, 'false_positive')}>Mark False Positive</button>
                  <button className="btn btn-danger" onClick={() => handleAction(selectedAlert.id, 'escalate')}>Escalate</button>
                </div>
              )}

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

              {selectedAlert.disagreement && (
                <div style={{ background: '#fef3c7', color: '#92400e', padding: '1rem', borderRadius: '0.5rem', marginBottom: '2rem' }}>
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
    </div>
  );
}

export default TriageInbox;

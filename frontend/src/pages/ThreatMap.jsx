import React, { useState, useEffect, useMemo, useCallback, useRef, Suspense, lazy } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-hot-toast';
import { Play } from 'lucide-react';
import CMDBWidget from '../components/CMDBWidget';
import ThreatGraph from '../components/ThreatGraph';
import EventDrillDownModal from '../components/EventDrillDownModal';

const ThreatGraph3D = lazy(() => import('../components/ThreatGraph3D'));

const ThreatMap = ({ token }) => {
  const navigate = useNavigate();
  const canMutate = localStorage.getItem('quantum_role') !== 'READ_ONLY';
  const [alerts, setAlerts] = useState([]);
  const alertsRef = useRef([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedIdentityId, setSelectedIdentityId] = useState(null);
  const [cmdbData, setCmdbData] = useState(null);
  const [selectedAlert, setSelectedAlert] = useState(null);
  const [viewMode, setViewMode] = useState('kanban'); // 'kanban' or '3d'

  const fetchAlerts = useCallback(async (signal) => {
    try {
      const res = await fetch('/api/alerts?status=open&limit=1000', {
        headers: { 'Authorization': `Bearer ${token}` },
        signal,
      });
      if (res.ok) {
        const data = await res.json();
        alertsRef.current = Array.isArray(data.alerts) ? data.alerts : [];
        setAlerts(alertsRef.current);
        setError(null);
      } else if (!signal?.aborted) {
        // Keep existing map on poll failure; only hard-fail initial load.
        setError(prev => (alertsRef.current.length === 0 ? 'Failed to fetch alerts' : prev));
        if (alertsRef.current.length > 0) toast.error('Failed to refresh threat map');
      }
    } catch (e) {
      if (e.name === 'AbortError') return;
      console.error(e);
      setError(prev => (alertsRef.current.length === 0 ? 'Connection error' : prev));
      if (alertsRef.current.length > 0) toast.error('Threat map refresh failed');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    const controller = new AbortController();
    fetchAlerts(controller.signal);
    let pollController;
    const interval = setInterval(() => {
      pollController?.abort();
      pollController = new AbortController();
      fetchAlerts(pollController.signal);
    }, 5000);
    return () => {
      controller.abort();
      pollController?.abort();
      clearInterval(interval);
    };
  }, [fetchAlerts]);

  useEffect(() => {
    if (!selectedIdentityId) {
      setCmdbData(null);
      return undefined;
    }
    const controller = new AbortController();
    fetch(`/api/cmdb/${encodeURIComponent(selectedIdentityId)}`, {
      headers: { 'Authorization': `Bearer ${token}` },
      signal: controller.signal,
    })
      .then(res => res.json())
      .then(data => setCmdbData(data))
      .catch(e => { if (e.name !== 'AbortError') console.error(e); });
    return () => controller.abort();
  }, [selectedIdentityId, token]);

  const handleCutOff = async (identity) => {
    try {
      const res = await fetch('/api/alerts/action', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ action: 'cut_off', identity })
      });
      if (res.ok) {
        toast.success(`Identity ${identity} cut off and suppressed.`);
        setSelectedIdentityId(null);
        fetchAlerts();
      } else {
        toast.error('Failed to cut off identity.');
      }
    } catch {
      toast.error('Error contacting server.');
    }
  };

  const handleAlertAction = async (alertId, actionStr) => {
    const res = await fetch(`/api/alert/${alertId}/action?action=${actionStr}`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });
    if (!res.ok) throw new Error('Failed');
    const data = await res.json().catch(() => ({}));
    fetchAlerts();
    if (actionStr === 'escalate' && data.case_id) {
      toast.success(data.message || `Escalated to CASE-${String(data.case_id).padStart(4, '0')}`);
      navigate(`/cases?caseId=${data.case_id}`);
    }
  };

  const identities = useMemo(() => {
    const map = {};
    alerts.forEach(a => {
      if (!map[a.identity]) {
        map[a.identity] = {
          identity: a.identity,
          short_identity: a.short_identity,
          cloud: a.cloud,
          phases: new Set(),
          maxScore: 0,
          latestTimestamp: a.timestamp,
          alerts: [],
          linked_identities: a.linked_identities || []
        };
      }
      map[a.identity].phases.add(a.attack_phase || 'Initial Access');
      map[a.identity].alerts.push(a);
      if (a.score > map[a.identity].maxScore) {
        map[a.identity].maxScore = a.score;
      }
      if (new Date(a.timestamp) > new Date(map[a.identity].latestTimestamp)) {
        map[a.identity].latestTimestamp = a.timestamp;
      }
    });
    return Object.values(map).sort((a, b) => b.maxScore - a.maxScore);
  }, [alerts]);

  const phases = ["Initial Access", "Discovery", "Credential Access", "Exfiltration"];

  const getSeverityColor = (score) => {
    if (score >= 0.85) return '#ef4444'; // Red
    if (score >= 0.75) return '#f97316'; // Orange
    if (score >= 0.68) return '#eab308'; // Yellow
    return '#22c55e'; // Green
  };

  const getSeverityLabel = (score) => {
    if (score >= 0.85) return 'Critical risk';
    if (score >= 0.75) return 'High Risk';
    if (score >= 0.68) return 'Suspicious';
    return 'Normal';
  };

  if (loading) {
    return (
      <div className="page-container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1rem' }}>
          <div className="spinner" style={{ width: 32, height: 32 }} />
          <div style={{ color: 'var(--text-secondary)' }}>Loading threat map…</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <div style={{ color: 'var(--danger)', textAlign: 'center' }}>
          <h2 style={{ margin: '0 0 0.5rem 0' }}>Threat map unavailable</h2>
          <p style={{ margin: 0 }}>{error}</p>
          <button className="btn btn-primary" onClick={() => fetchAlerts()} style={{ marginTop: '1rem' }}>Retry</button>
        </div>
      </div>
    );
  }

  const selectedIdentity = identities.find(id => id.identity === selectedIdentityId);

  return (
    <div className="page-container" style={{ display: 'flex', flexDirection: 'column', height: '100%', padding: '0' }}>
      <header className="page-header">
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' }}>
          <div>
            <h1 className="page-title">Threat map</h1>
            <p className="page-subtitle">
              Review identity activity by observed attack phase and relationship.
            </p>
          </div>
          <div className="page-actions">
            <div className="segmented-control" aria-label="Threat map view">
              <button 
                onClick={() => setViewMode('kanban')} 
                className={viewMode === 'kanban' ? 'is-active' : ''}
                aria-pressed={viewMode === 'kanban'}
              >
                Phases
              </button>
              <button 
                onClick={() => setViewMode('3d')} 
                className={viewMode === '3d' ? 'is-active' : ''}
                aria-pressed={viewMode === '3d'}
              >
                Network
              </button>
            </div>
            {canMutate && (
              <button
                className="btn btn-primary"
                onClick={async () => {
                const res = await fetch('/api/replay_attack', {
                  method: 'POST',
                  headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json',
                  },
                  body: JSON.stringify({ kind: 'mixed', count: 8 }),
                });
                if (res.ok) {
                  const data = await res.json();
                  toast.success(data.message || 'Test scenario queued');
                } else {
                  const err = await res.json().catch(() => ({}));
                  toast.error(err.message || 'Replay failed');
                }
                }}
              >
                <Play size={15} /> Run test scenario
              </button>
            )}
          </div>
        </div>
      </header>
      
      <div className="threat-map-layout" style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        {viewMode === 'kanban' ? (
          <ThreatGraph 
            phases={phases}
            identities={identities}
            selectedIdentityId={selectedIdentityId}
            setSelectedIdentityId={setSelectedIdentityId}
            getSeverityColor={getSeverityColor}
          />
        ) : (
          <Suspense fallback={<p style={{ color: 'var(--text-secondary)', padding: '2rem' }}>Loading 3D graph…</p>}>
            <ThreatGraph3D
              alerts={alerts}
              selectedIdentityId={selectedIdentityId}
              setSelectedIdentityId={setSelectedIdentityId}
              getSeverityColor={getSeverityColor}
            />
          </Suspense>
        )}

        <CMDBWidget 
          selectedIdentity={selectedIdentity}
          cmdbData={cmdbData}
          getSeverityColor={getSeverityColor}
          getSeverityLabel={getSeverityLabel}
          handleCutOff={canMutate ? handleCutOff : null}
          phases={phases}
          onSelectAlert={(alert) => setSelectedAlert(alert)}
        />
      </div>

      <EventDrillDownModal 
        alert={selectedAlert}
        onClose={() => setSelectedAlert(null)}
        onAction={handleAlertAction}
        getSeverityColor={getSeverityColor}
      />
    </div>
  );
};

export default ThreatMap;

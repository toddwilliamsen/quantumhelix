import React, { useState, useEffect, useMemo } from 'react';
import { toast } from 'react-hot-toast';
import { Play } from 'lucide-react';
import CMDBWidget from '../components/CMDBWidget';
import ThreatGraph from '../components/ThreatGraph';
import ThreatGraph3D from '../components/ThreatGraph3D';
import EventDrillDownModal from '../components/EventDrillDownModal';

const ThreatMap = ({ token }) => {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedIdentityId, setSelectedIdentityId] = useState(null);
  const [cmdbData, setCmdbData] = useState(null);
  const [selectedAlert, setSelectedAlert] = useState(null);
  const [viewMode, setViewMode] = useState('kanban'); // 'kanban' or '3d'

  const fetchAlerts = async () => {
    try {
      const res = await fetch('/api/alerts?status=open&limit=1000', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (res.ok) {
        const data = await res.json();
        setAlerts(data.alerts);
        setError(null);
      } else {
        setError('Failed to fetch alerts');
      }
    } catch (e) {
      console.error(e);
      setError('Connection error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAlerts();
    const interval = setInterval(fetchAlerts, 5000);
    return () => clearInterval(interval);
  }, [token]);

  useEffect(() => {
    if (selectedIdentityId) {
      fetch(`/api/cmdb/${encodeURIComponent(selectedIdentityId)}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      .then(res => res.json())
      .then(data => setCmdbData(data))
      .catch(e => console.error(e));
    } else {
      setCmdbData(null);
    }
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
    } catch (e) {
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
    fetchAlerts();
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
    if (score >= 0.85) return 'Quantum-Confirmed Anomaly';
    if (score >= 0.75) return 'High Risk';
    if (score >= 0.68) return 'Suspicious';
    return 'Normal';
  };

  if (loading) {
    return (
      <div className="page-container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1rem' }}>
          <div className="spinner" style={{ border: '4px solid var(--border-color)', borderTopColor: 'var(--text-primary)', borderRadius: '50%', width: '40px', height: '40px', animation: 'spin 1s linear infinite' }} />
          <div style={{ color: 'var(--text-secondary)' }}>Loading Threat Map...</div>
          <style>{`@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }`}</style>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <div style={{ color: '#ef4444', textAlign: 'center' }}>
          <h2 style={{ margin: '0 0 0.5rem 0' }}>Error Loading Data</h2>
          <p style={{ margin: 0 }}>{error}</p>
          <button className="btn btn-primary" onClick={fetchAlerts} style={{ marginTop: '1rem' }}>Retry</button>
        </div>
      </div>
    );
  }

  const selectedIdentity = identities.find(id => id.identity === selectedIdentityId);
  const selectedLatestAlert = selectedIdentity?.alerts[0]; // Alerts are sorted desc by default

  return (
    <div className="page-container" style={{ display: 'flex', flexDirection: 'column', height: '100%', padding: '0' }}>
      <header className="page-header" style={{ padding: '1.5rem 1.5rem 0 1.5rem', marginBottom: '1rem' }}>
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <h1 style={{ margin: 0 }}>Predictive Threat Map (Kill Chain)</h1>
            <p style={{ margin: '0.5rem 0 0 0', color: 'var(--text-secondary)' }}>
              Track identities as they move through MITRE ATT&CK phases. Cut off access before they reach Exfiltration.
            </p>
          </div>
          <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
            <div style={{ display: 'flex', background: 'var(--bg-secondary)', borderRadius: '4px', padding: '0.25rem' }}>
              <button 
                onClick={() => setViewMode('kanban')} 
                style={{ padding: '0.5rem 1rem', background: viewMode === 'kanban' ? 'var(--bg-primary)' : 'transparent', color: viewMode === 'kanban' ? 'var(--text-primary)' : 'var(--text-secondary)', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: viewMode === 'kanban' ? 600 : 400 }}
              >
                Kanban
              </button>
              <button 
                onClick={() => setViewMode('3d')} 
                style={{ padding: '0.5rem 1rem', background: viewMode === '3d' ? 'var(--bg-primary)' : 'transparent', color: viewMode === '3d' ? 'var(--text-primary)' : 'var(--text-secondary)', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: viewMode === '3d' ? 600 : 400 }}
              >
                3D WebGL
              </button>
            </div>
            <button 
              className="btn btn-primary" 
              onClick={async () => {
                const res = await fetch('/api/replay_attack', { method: 'POST', headers: { 'Authorization': `Bearer ${token}` }});
                if (res.ok) {
                  toast.success("Synthetic attack injected!", { icon: '💉' });
                }
              }}
              style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
            >
              <Play size={16} /> Replay Synthetic Attack
            </button>
          </div>
        </div>
      </header>
      
      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        {viewMode === 'kanban' ? (
          <ThreatGraph 
            phases={phases}
            identities={identities}
            selectedIdentityId={selectedIdentityId}
            setSelectedIdentityId={setSelectedIdentityId}
            getSeverityColor={getSeverityColor}
          />
        ) : (
          <ThreatGraph3D 
            alerts={alerts}
            selectedIdentityId={selectedIdentityId}
            setSelectedIdentityId={setSelectedIdentityId}
            getSeverityColor={getSeverityColor}
          />
        )}

        <CMDBWidget 
          selectedIdentity={selectedIdentity}
          cmdbData={cmdbData}
          selectedLatestAlert={selectedLatestAlert}
          getSeverityColor={getSeverityColor}
          getSeverityLabel={getSeverityLabel}
          handleCutOff={handleCutOff}
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

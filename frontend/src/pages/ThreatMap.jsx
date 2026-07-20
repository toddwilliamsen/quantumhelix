import React, { useState, useEffect, useMemo } from 'react';
import { toast } from 'react-hot-toast';
import { Activity, ShieldOff, Cloud, Clock, CheckCircle2, AlertTriangle, AlertCircle, Play } from 'lucide-react';
import InfoBubble from '../components/InfoBubble';

const ThreatMap = ({ token }) => {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedIdentityId, setSelectedIdentityId] = useState(null);
  const [cmdbData, setCmdbData] = useState(null);

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
      }
    } catch (e) {
      console.error(e);
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

  // Group alerts by identity
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
    return <div className="page-container">Loading Threat Map...</div>;
  }

  const selectedIdentity = identities.find(id => id.identity === selectedIdentityId);
  const selectedLatestAlert = selectedIdentity?.alerts[0]; // Alerts are sorted desc by default

  return (
    <div className="page-container" style={{ display: 'flex', flexDirection: 'column', height: '100%', padding: '0' }}>
      <header className="page-header" style={{ padding: '1.5rem 1.5rem 0 1.5rem', marginBottom: '1rem' }}>
        <div style={{ flex: 1 }}>
          <h1 style={{ margin: 0 }}>Predictive Threat Map (Kill Chain)</h1>
          <p style={{ margin: '0.5rem 0 0 0', color: 'var(--text-secondary)' }}>
            Track identities as they move through MITRE ATT&CK phases. Cut off access before they reach Exfiltration.
          </p>
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
      </header>
      
      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        {/* Main Kill Chain Board */}
        <div style={{ flex: 1, display: 'flex', gap: '1rem', overflowX: 'auto', padding: '0 1.5rem 1.5rem 1.5rem' }}>
          {phases.map((phase, idx) => (
            <div key={phase} style={{ flex: 1, minWidth: '260px', background: 'var(--bg-secondary)', borderRadius: '8px', padding: '1rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <h3 style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em', display: 'flex', alignItems: 'center', gap: '0.5rem', margin: 0 }}>
                <span style={{ background: 'var(--bg-primary)', width: '20px', height: '20px', display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: '50%', fontSize: '0.7rem' }}>{idx + 1}</span> 
                {phase}
              </h3>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', flex: 1 }}>
                {identities.filter(idObj => {
                  const highestPhaseIdx = Math.max(...Array.from(idObj.phases).map(p => phases.indexOf(p)));
                  return phases.indexOf(phase) === highestPhaseIdx;
                }).map(idObj => {
                  const color = getSeverityColor(idObj.maxScore);
                  const isSelected = selectedIdentityId === idObj.identity;
                  
                  return (
                    <div 
                      key={idObj.identity} 
                      onClick={() => setSelectedIdentityId(idObj.identity)}
                      style={{
                        background: 'var(--bg-primary)',
                        border: `1px solid ${isSelected ? color : 'var(--border-color)'}`,
                        borderRadius: '8px',
                        padding: '1rem',
                        boxShadow: isSelected ? `0 0 0 1px ${color}` : '0 1px 3px rgba(0,0,0,0.1)',
                        cursor: 'pointer',
                        transition: 'transform 0.1s ease, box-shadow 0.1s ease',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '0.75rem'
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.transform = 'translateY(-2px)';
                        e.currentTarget.style.boxShadow = isSelected ? `0 4px 12px ${color}66` : '0 4px 12px rgba(0,0,0,0.15)';
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.transform = 'none';
                        e.currentTarget.style.boxShadow = isSelected ? `0 0 0 1px ${color}` : '0 1px 3px rgba(0,0,0,0.1)';
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', overflow: 'hidden' }}>
                          <Activity size={16} color={color} />
                          <span style={{ fontWeight: 600, fontSize: '0.9rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={idObj.identity}>
                            {idObj.short_identity}
                          </span>
                        </div>
                      </div>
                      
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                        <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                          <Cloud size={12} /> {idObj.cloud}
                        </span>
                        <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                          <Clock size={12} /> {new Date(idObj.latestTimestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <div style={{ flex: 1, height: '6px', background: 'var(--bg-secondary)', borderRadius: '3px', overflow: 'hidden' }}>
                          <div style={{ width: `${Math.min(idObj.maxScore * 100, 100)}%`, height: '100%', background: color }} />
                        </div>
                        <span style={{ fontSize: '0.75rem', fontWeight: 600, color: color }}>
                          {idObj.maxScore.toFixed(3)}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        {/* Right-Side Detail Panel */}
        {selectedIdentity && (
          <div style={{ width: '400px', background: 'var(--bg-secondary)', borderLeft: '1px solid var(--border-color)', display: 'flex', flexDirection: 'column' }}>
            <div style={{ padding: '1.5rem', borderBottom: '1px solid var(--border-color)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
                <Activity size={20} color={getSeverityColor(selectedIdentity.maxScore)} />
                <h2 style={{ margin: 0, fontSize: '1.1rem', wordBreak: 'break-all' }}>{selectedIdentity.short_identity}</h2>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem' }}>
                <span style={{ fontSize: '0.75rem', background: 'var(--bg-primary)', padding: '0.2rem 0.5rem', borderRadius: '4px', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                  <Cloud size={12} /> {selectedIdentity.cloud}
                </span>
                <span style={{ fontSize: '0.75rem', background: getSeverityColor(selectedIdentity.maxScore) + '22', color: getSeverityColor(selectedIdentity.maxScore), padding: '0.2rem 0.5rem', borderRadius: '4px', fontWeight: 600 }}>
                  {getSeverityLabel(selectedIdentity.maxScore)}
                </span>
              </div>

              {cmdbData && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginBottom: '1.5rem', padding: '1rem', background: 'var(--bg-primary)', borderRadius: '6px', border: '1px solid var(--border-color)' }}>
                  <div style={{ fontSize: '0.75rem', color: '#6366f1', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                    <Cloud size={14} /> Asset Context (CMDB)
                  </div>
                  <div style={{ fontSize: '0.85rem' }}>
                    <strong>Owner:</strong> {cmdbData.owner} ({cmdbData.department})
                  </div>
                  <div style={{ fontSize: '0.85rem' }}>
                    <strong>Type:</strong> {cmdbData.asset_type}
                  </div>
                  <div style={{ fontSize: '0.85rem' }}>
                    <strong>Criticality:</strong> {cmdbData.business_criticality}
                  </div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                    {cmdbData.description}
                  </div>
                </div>
              )}
              
              <button 
                className="btn"
                onClick={() => handleCutOff(selectedIdentity.identity)}
                style={{ 
                  width: '100%', 
                  background: '#ef4444', 
                  color: 'white', 
                  border: 'none', 
                  display: 'flex', 
                  alignItems: 'center', 
                  justifyContent: 'center', 
                  gap: '0.5rem',
                  padding: '0.75rem'
                }}
              >
                <ShieldOff size={16} /> Contain Identity (Cut Off)
              </button>
            </div>

            <div style={{ flex: 1, overflowY: 'auto', padding: '1.5rem' }}>
              <h3 style={{ fontSize: '0.85rem', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '1rem', letterSpacing: '0.05em' }}>Kill Chain Progression</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginBottom: '2rem', position: 'relative' }}>
                <div style={{ position: 'absolute', left: '11px', top: '10px', bottom: '10px', width: '2px', background: 'var(--border-color)', zIndex: 0 }} />
                {phases.map((p, i) => {
                  const reached = selectedIdentity.phases.has(p);
                  return (
                    <div key={p} style={{ display: 'flex', alignItems: 'center', gap: '1rem', position: 'relative', zIndex: 1, opacity: reached ? 1 : 0.4 }}>
                      <div style={{ width: '24px', height: '24px', borderRadius: '50%', background: reached ? getSeverityColor(selectedIdentity.maxScore) : 'var(--bg-primary)', border: `2px solid ${reached ? getSeverityColor(selectedIdentity.maxScore) : 'var(--border-color)'}`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        {reached && <CheckCircle2 size={14} color="white" />}
                      </div>
                      <span style={{ fontSize: '0.85rem', fontWeight: reached ? 600 : 400 }}>{p}</span>
                    </div>
                  );
                })}
              </div>

              {selectedIdentity.linked_identities && selectedIdentity.linked_identities.length > 0 && (
                <>
                  <h3 style={{ fontSize: '0.85rem', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '1rem', letterSpacing: '0.05em' }}>Identity Lineage</h3>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginBottom: '2rem', background: 'var(--bg-primary)', padding: '1rem', borderRadius: '8px', border: '1px dashed #3b82f6' }}>
                    <div style={{ fontSize: '0.75rem', color: '#3b82f6', marginBottom: '0.5rem' }}>Cross-Cloud Correlation Detected</div>
                    {selectedIdentity.linked_identities.map((lid, idx) => (
                      <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8rem' }}>
                        <Cloud size={14} color="#8b5cf6" />
                        <span>{lid}</span>
                      </div>
                    ))}
                  </div>
                </>
              )}

              {selectedLatestAlert && (
                <>
                  <h3 style={{ fontSize: '0.85rem', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '1rem', letterSpacing: '0.05em' }}>Quantum Context</h3>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '1.5rem' }}>
                    <div style={{ background: 'var(--bg-primary)', padding: '0.75rem', borderRadius: '6px' }}>
                      <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>Quantum Kernel SVM</div>
                      <div style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)' }}>{selectedLatestAlert.quantum_kernel.toFixed(3)}</div>
                    </div>
                    <div style={{ background: 'var(--bg-primary)', padding: '0.75rem', borderRadius: '6px' }}>
                      <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>Classical SVM</div>
                      <div style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)' }}>{selectedLatestAlert.classical_svm.toFixed(3)}</div>
                    </div>
                    <div style={{ background: 'var(--bg-primary)', padding: '0.75rem', borderRadius: '6px' }}>
                      <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>Isolation Forest</div>
                      <div style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)' }}>{selectedLatestAlert.isolation_forest.toFixed(3)}</div>
                    </div>
                    <div style={{ background: 'var(--bg-primary)', padding: '0.75rem', borderRadius: '6px', border: `1px solid ${getSeverityColor(selectedLatestAlert.ensemble)}` }}>
                      <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>Ensemble Score</div>
                      <div style={{ fontSize: '1.1rem', fontWeight: 600, color: getSeverityColor(selectedLatestAlert.ensemble) }}>{selectedLatestAlert.ensemble.toFixed(3)}</div>
                    </div>
                  </div>

                  {selectedLatestAlert.disagreement && (
                    <div style={{ background: '#fef3c7', border: '1px solid #fbbf24', padding: '0.75rem', borderRadius: '6px', fontSize: '0.8rem', color: '#b45309', marginBottom: '1.5rem', display: 'flex', gap: '0.5rem', alignItems: 'flex-start' }}>
                      <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: '0.1rem' }} />
                      <span>{selectedLatestAlert.disagreement}</span>
                    </div>
                  )}

                  {selectedLatestAlert.feature_contributions && (
                    <>
                      <h3 style={{ fontSize: '0.85rem', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '1rem', letterSpacing: '0.05em' }}>Anomaly Context (Feature Contributions)</h3>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginBottom: '1.5rem', fontSize: '0.85rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.5rem', background: 'var(--bg-primary)', borderRadius: '4px' }}>
                          <span style={{ color: 'var(--text-secondary)' }}>API Velocity</span>
                          <span style={{ fontWeight: 600 }}>{selectedLatestAlert.feature_contributions.api_velocity.toFixed(1)} req/s</span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.5rem', background: 'var(--bg-primary)', borderRadius: '4px' }}>
                          <span style={{ color: 'var(--text-secondary)' }}>Auth Failures</span>
                          <span style={{ fontWeight: 600 }}>{selectedLatestAlert.feature_contributions.auth_failures.toFixed(1)}</span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.5rem', background: 'var(--bg-primary)', borderRadius: '4px' }}>
                          <span style={{ color: 'var(--text-secondary)' }}>Data Volume</span>
                          <span style={{ fontWeight: 600 }}>{(selectedLatestAlert.feature_contributions.data_volume_bytes / 1e6).toFixed(2)} MB</span>
                        </div>
                      </div>
                    </>
                  )}

                  {selectedLatestAlert.auto_response && (
                    <div style={{ background: '#ecfdf5', border: '1px solid #10b981', padding: '0.75rem', borderRadius: '6px', fontSize: '0.8rem', color: '#065f46', marginBottom: '1.5rem', display: 'flex', gap: '0.5rem', alignItems: 'flex-start' }}>
                      <Activity size={16} style={{ flexShrink: 0, marginTop: '0.1rem' }} />
                      <div style={{ flex: 1 }}>
                        <strong>Automated Policy Response Triggered:</strong><br/>
                        {selectedLatestAlert.auto_response}
                      </div>
                      {selectedLatestAlert.itsm_ticket && (
                        <div style={{ background: '#065f46', color: 'white', padding: '0.2rem 0.5rem', borderRadius: '4px', fontSize: '0.7rem', fontWeight: 600 }}>
                          {selectedLatestAlert.itsm_ticket}
                        </div>
                      )}
                    </div>
                  )}

                  <h3 style={{ fontSize: '0.85rem', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '1rem', letterSpacing: '0.05em' }}>Recommended Actions</h3>
                  <ul style={{ margin: 0, paddingLeft: '1.25rem', fontSize: '0.85rem', color: 'var(--text-primary)', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                    {selectedLatestAlert.actions.map((act, i) => (
                      <li key={i}>{act}</li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ThreatMap;

import React from 'react';
import { Cloud, Activity, CheckCircle2, AlertTriangle } from 'lucide-react';

const CMDBWidget = ({ selectedIdentity, cmdbData, getSeverityColor, getSeverityLabel, handleCutOff, phases, onSelectAlert }) => {
  if (!selectedIdentity) return null;

  return (
    <div className="cmdb-panel" style={{ width: '400px', background: 'var(--bg-secondary)', borderLeft: '1px solid var(--border-color)', display: 'flex', flexDirection: 'column' }}>
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
        
        {handleCutOff && (
          <button
            className="btn btn-danger"
            onClick={() => handleCutOff(selectedIdentity.identity)}
            style={{ width: '100%' }}
          >
            Contain identity
          </button>
        )}
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '1.5rem' }}>
        <h3 style={{ fontSize: '0.85rem', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '1rem', letterSpacing: '0.05em' }}>Kill Chain Progression</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginBottom: '2rem', position: 'relative' }}>
          <div style={{ position: 'absolute', left: '11px', top: '10px', bottom: '10px', width: '2px', background: 'var(--border-color)', zIndex: 0 }} />
          {phases.map((p) => {
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

        {selectedIdentity.alerts && selectedIdentity.alerts.length > 0 && (
          <>
            <h3 style={{ fontSize: '0.85rem', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '1rem', letterSpacing: '0.05em' }}>Alert Timeline</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginBottom: '1.5rem' }}>
              {selectedIdentity.alerts.map((alert) => (
                <div 
                  key={alert.id}
                  onClick={() => onSelectAlert(alert)}
                  style={{
                    background: 'var(--bg-primary)',
                    border: '1px solid var(--border-color)',
                    borderRadius: '8px',
                    padding: '1rem',
                    cursor: 'pointer',
                    transition: 'transform 0.1s ease, box-shadow 0.1s ease',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.transform = 'translateY(-2px)';
                    e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.1)';
                    e.currentTarget.style.borderColor = getSeverityColor(alert.score);
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.transform = 'none';
                    e.currentTarget.style.boxShadow = 'none';
                    e.currentTarget.style.borderColor = 'var(--border-color)';
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                      {new Date(alert.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                    </span>
                    <span style={{ fontSize: '0.75rem', background: getSeverityColor(alert.score) + '22', color: getSeverityColor(alert.score), padding: '0.1rem 0.4rem', borderRadius: '4px', fontWeight: 600 }}>
                      Score: {alert.score.toFixed(3)}
                    </span>
                  </div>
                  <div style={{ fontSize: '0.85rem', fontWeight: 500, color: 'var(--text-primary)', marginBottom: '0.25rem' }}>
                    {alert.attack_phase} Detected
                  </div>
                  {alert.disagreement && (
                    <div style={{ fontSize: '0.75rem', color: '#b45309', display: 'flex', alignItems: 'center', gap: '0.25rem', marginTop: '0.5rem' }}>
                      <AlertTriangle size={12} /> Model Disagreement
                    </div>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default CMDBWidget;

import React from 'react';
import { Cloud, Activity, CheckCircle2, AlertTriangle } from 'lucide-react';

const CMDBWidget = ({ selectedIdentity, cmdbData, selectedLatestAlert, getSeverityColor, getSeverityLabel, handleCutOff, phases }) => {
  if (!selectedIdentity) return null;

  return (
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
          Contain Identity (Cut Off)
        </button>
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
  );
};

export default CMDBWidget;

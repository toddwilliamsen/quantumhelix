import React from 'react';
import { X, Activity, Shield, Code, Server, AlertTriangle, Play } from 'lucide-react';
import { toast } from 'react-hot-toast';

const EventDrillDownModal = ({ alert, onClose, onAction, getSeverityColor }) => {
  if (!alert) return null;

  const handleAction = async (actionStr) => {
    try {
      await onAction(alert.id, actionStr);
      toast.success(`Event marked as ${actionStr}`);
      onClose();
    } catch (e) {
      toast.error('Failed to update event');
    }
  };

  const rawJson = JSON.stringify(alert, null, 2);

  return (
    <div style={{
      position: 'fixed',
      top: 0, left: 0, right: 0, bottom: 0,
      background: 'rgba(0,0,0,0.5)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000,
      backdropFilter: 'blur(4px)'
    }}>
      <div style={{
        background: 'var(--bg-color)',
        borderRadius: '12px',
        width: '90%',
        maxWidth: '900px',
        maxHeight: '90vh',
        display: 'flex',
        flexDirection: 'column',
        boxShadow: 'var(--shadow-md)',
        overflow: 'hidden'
      }}>
        {/* Header */}
        <div style={{
          padding: '1.5rem',
          borderBottom: '1px solid var(--border-color)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          background: 'var(--surface)'
        }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
              <Activity color={getSeverityColor(alert.score)} size={24} />
              <h2 style={{ margin: 0 }}>Event Drill-Down</h2>
            </div>
            <div style={{ display: 'flex', gap: '1rem', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
              <span>ID: {alert.id}</span>
              <span>•</span>
              <span>{new Date(alert.timestamp).toLocaleString()}</span>
              <span>•</span>
              <span style={{ color: getSeverityColor(alert.score), fontWeight: 600 }}>Score: {alert.score.toFixed(3)}</span>
            </div>
          </div>
          <button 
            onClick={onClose}
            style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: '0.5rem' }}
          >
            <X size={20} color="var(--text-secondary)" />
          </button>
        </div>

        {/* Content */}
        <div style={{ padding: '1.5rem', overflowY: 'auto', flex: 1, display: 'flex', gap: '2rem' }}>
          
          {/* Left Column */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <div>
              <h3 style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', textTransform: 'uppercase', marginBottom: '1rem' }}>Detector Consensus</h3>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--bg-primary)', padding: '1rem', borderRadius: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}><Server size={16} /> Classical SVM</div>
                  <div style={{ fontWeight: 600, fontSize: '1.1rem' }}>{alert.classical_svm.toFixed(3)}</div>
                </div>
                
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--bg-primary)', padding: '1rem', borderRadius: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}><Play size={16} /> Isolation Forest</div>
                  <div style={{ fontWeight: 600, fontSize: '1.1rem' }}>{alert.isolation_forest.toFixed(3)}</div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#3b82f615', border: '1px solid #3b82f644', padding: '1rem', borderRadius: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#3b82f6' }}><Activity size={16} /> Quantum Kernel</div>
                  <div style={{ fontWeight: 600, fontSize: '1.1rem', color: '#3b82f6' }}>{alert.quantum_kernel.toFixed(3)}</div>
                </div>
              </div>
              
              {alert.disagreement && (
                <div style={{ marginTop: '1rem', padding: '1rem', background: '#fef3c7', border: '1px solid #fbbf24', borderRadius: '8px', color: '#b45309', fontSize: '0.85rem', display: 'flex', gap: '0.75rem', alignItems: 'flex-start' }}>
                  <AlertTriangle size={18} style={{ flexShrink: 0 }} />
                  <div>
                    <strong>Disagreement Detected:</strong> {alert.disagreement}
                  </div>
                </div>
              )}
            </div>

            <div>
              <h3 style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', textTransform: 'uppercase', marginBottom: '1rem' }}>Anomaly Context</h3>
              <p style={{ fontSize: '0.9rem', lineHeight: '1.5' }}>{alert.plain_english}</p>
              
              <ul style={{ margin: '1rem 0 0 0', paddingLeft: '1.5rem', fontSize: '0.85rem', color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {alert.actions.map((act, i) => <li key={i}>{act}</li>)}
              </ul>
            </div>
          </div>

          {/* Right Column (Raw Telemetry) */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
            <h3 style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', textTransform: 'uppercase', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Code size={16} /> Raw Telemetry
            </h3>
            <div style={{ 
              background: '#1e293b', 
              color: '#e2e8f0', 
              padding: '1rem', 
              borderRadius: '8px', 
              fontFamily: 'monospace', 
              fontSize: '0.8rem',
              overflowY: 'auto',
              flex: 1,
              whiteSpace: 'pre-wrap',
              border: '1px solid #334155'
            }}>
              {rawJson}
            </div>
          </div>

        </div>

        {/* Footer Actions */}
        <div style={{
          padding: '1.5rem',
          borderTop: '1px solid var(--border-color)',
          background: 'var(--surface)',
          display: 'flex',
          justifyContent: 'flex-end',
          gap: '1rem'
        }}>
          <button className="btn" onClick={() => handleAction('false_positive')} style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}>
            Mark False Positive
          </button>
          <button className="btn" onClick={() => handleAction('acknowledge')} style={{ background: '#3b82f6', color: 'white', border: 'none' }}>
            Acknowledge (Benign)
          </button>
          <button className="btn" onClick={() => handleAction('escalate')} style={{ background: '#ef4444', color: 'white', border: 'none', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Shield size={16} /> Escalate Alert
          </button>
        </div>
      </div>
    </div>
  );
};

export default EventDrillDownModal;

import React, { useState, useEffect } from 'react';
import { X, Activity, Shield, Code, Server, Play, Sparkles, Globe } from 'lucide-react';
import { toast } from 'react-hot-toast';
import { useFocusTrap } from '../hooks/useFocusTrap';
import IntrusionExplanation from './IntrusionExplanation';

/** Safely render light markdown (**bold**, `code`, newlines) without HTML injection. */
function SafeInsight({ text }) {
  if (!text) return null;
  const parts = String(text).split(/(\*\*[^*]+\*\*|`[^`]+`|\n)/g);
  return (
    <div style={{ padding: '1rem', background: 'var(--bg-primary)', border: '1px solid var(--border-color)', borderRadius: '8px', marginBottom: '1rem', color: 'var(--text-primary)', fontSize: '0.85rem', lineHeight: '1.5' }}>
      {parts.map((part, i) => {
        if (part === '\n') return <br key={i} />;
        if (part.startsWith('**') && part.endsWith('**')) {
          return <strong key={i}>{part.slice(2, -2)}</strong>;
        }
        if (part.startsWith('`') && part.endsWith('`')) {
          return <code key={i} style={{ background: 'var(--border-color)', padding: '2px 4px', borderRadius: '4px' }}>{part.slice(1, -1)}</code>;
        }
        return <React.Fragment key={i}>{part}</React.Fragment>;
      })}
    </div>
  );
}

const EventDrillDownModal = ({ alert, onClose, onAction, getSeverityColor }) => {
  const dialogRef = useFocusTrap(!!alert);
  const [aiInsight, setAiInsight] = useState(null);
  const [loadingAi, setLoadingAi] = useState(false);
  const [osintData, setOsintData] = useState(null);
  const [loadingOsint, setLoadingOsint] = useState(false);
  const [explainedAlert, setExplainedAlert] = useState(alert);

  useEffect(() => {
    setAiInsight(null);
    setOsintData(null);
    setLoadingAi(false);
    setLoadingOsint(false);
    setExplainedAlert(alert);
  }, [alert?.id]);

  useEffect(() => {
    if (!alert) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [alert, onClose]);

  if (!alert) return null;

  const view = explainedAlert || alert;
  const token = localStorage.getItem('quantum_token');
  const role = localStorage.getItem('quantum_role');
  const actions = Array.isArray(view.actions) ? view.actions : [];
  const osintTags = Array.isArray(osintData?.tags) ? osintData.tags : [];

  const fetchAiInsight = async () => {
    setLoadingAi(true);
    try {
      const res = await fetch('/api/ai-insight', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ alert_id: alert.id })
      });
      if (res.ok) {
        const data = await res.json();
        setAiInsight(data.insight);
        if (data.explanation) {
          setExplainedAlert({
            ...view,
            feature_contributions: data.explanation,
            plain_english: data.explanation.narrative || view.plain_english,
            disagreement: data.explanation.disagreement_text || view.disagreement,
            attack_phase: data.explanation.attack_phase || view.attack_phase,
            actions: data.explanation.actions || view.actions,
          });
        }
      } else toast.error('Explanation failed');
    } catch { toast.error('Error building explanation'); }
    finally { setLoadingAi(false); }
  };

  const fetchOsint = async () => {
    setLoadingOsint(true);
    try {
      const res = await fetch(`/api/osint/${view.source_ip}`, { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) setOsintData(await res.json());
      else toast.error('OSINT lookup failed');
    } catch { toast.error('Error fetching OSINT'); }
    finally { setLoadingOsint(false); }
  };

  const handleAction = async (actionStr) => {
    try {
      await onAction(alert.id, actionStr);
      toast.success(`Event marked as ${actionStr}`);
      onClose();
    } catch {
      toast.error('Failed to update event');
    }
  };

  const rawJson = JSON.stringify(view, null, 2);

  return (
    <div
      role="presentation"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      style={{
      position: 'fixed',
      top: 0, left: 0, right: 0, bottom: 0,
      background: 'rgba(0,0,0,0.5)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000,
      backdropFilter: 'blur(4px)'
    }}>
      <div
        ref={dialogRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby="event-dialog-title"
        style={{
        background: 'var(--bg-color)',
        borderRadius: '12px',
        width: '90%',
        maxWidth: '900px',
        maxHeight: '90vh',
        display: 'flex',
        flexDirection: 'column',
        boxShadow: 'var(--shadow-md)',
        overflow: 'hidden',
        outline: 'none',
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
              <Activity color={getSeverityColor(view.score)} size={24} />
              <h2 id="event-dialog-title" style={{ margin: 0 }}>Event Drill-Down</h2>
            </div>
            <div style={{ display: 'flex', gap: '1rem', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
              <span>ID: {alert.id}</span>
              <span>•</span>
              <span>{new Date(alert.timestamp).toLocaleString()}</span>
              <span>•</span>
              <span style={{ color: getSeverityColor(view.score), fontWeight: 600 }}>Score: {view.score.toFixed(3)}</span>
            </div>
          </div>
          <button 
            onClick={onClose}
            aria-label="Close event details"
            style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: '0.5rem' }}
          >
            <X size={20} color="var(--text-secondary)" />
          </button>
        </div>

        {/* Content */}
        <div className="modal-columns" style={{ padding: '1.5rem', overflowY: 'auto', flex: 1, display: 'flex', gap: '2rem' }}>
          
          {/* Left Column */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <div>
              <h3 style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', textTransform: 'uppercase', marginBottom: '1rem' }}>Detector Consensus</h3>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--bg-primary)', padding: '1rem', borderRadius: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}><Server size={16} /> Classical SVM</div>
                  <div style={{ fontWeight: 600, fontSize: '1.1rem', fontFamily: 'var(--font-mono)' }}>{view.classical_svm.toFixed(3)}</div>
                </div>
                
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--bg-primary)', padding: '1rem', borderRadius: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}><Play size={16} /> Isolation Forest</div>
                  <div style={{ fontWeight: 600, fontSize: '1.1rem', fontFamily: 'var(--font-mono)' }}>{view.isolation_forest.toFixed(3)}</div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--primary-subtle)', border: '1px solid color-mix(in srgb, var(--primary) 35%, transparent)', padding: '1rem', borderRadius: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--primary)' }}><Activity size={16} /> Quantum Kernel</div>
                  <div style={{ fontWeight: 600, fontSize: '1.1rem', color: 'var(--primary)', fontFamily: 'var(--font-mono)' }}>{view.quantum_kernel.toFixed(3)}</div>
                </div>
              </div>
            </div>

            <IntrusionExplanation alert={view} />

            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                <h3 style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', textTransform: 'uppercase', margin: 0 }}>Analyst brief</h3>
                <button onClick={fetchAiInsight} disabled={loadingAi || aiInsight} className="btn btn-secondary" style={{ padding: '0.25rem 0.75rem', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                  <Sparkles size={14} /> {loadingAi ? 'Building…' : 'Generate explanation'}
                </button>
              </div>
              
              {aiInsight && <SafeInsight text={aiInsight} />}
              
              <ul style={{ margin: '1rem 0 0 0', paddingLeft: '1.5rem', fontSize: '0.85rem', color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {actions.map((act, i) => <li key={i}>{act}</li>)}
              </ul>
            </div>
            
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                <h3 style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', textTransform: 'uppercase', margin: 0 }}>Source OSINT</h3>
                <button onClick={fetchOsint} disabled={loadingOsint || osintData} className="btn btn-secondary" style={{ padding: '0.25rem 0.75rem', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                  <Globe size={14} /> {loadingOsint ? 'Lookup...' : 'Check Threat Intel'}
                </button>
              </div>
              
              {osintData && (
                <div style={{ padding: '1rem', background: 'var(--bg-primary)', borderRadius: '8px', border: `1px solid ${osintData.vendors_flagged > 0 ? '#ef4444' : 'var(--border-color)'}` }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                    <strong>{osintData.ip}</strong>
                    <span style={{ color: osintData.vendors_flagged > 0 ? '#ef4444' : 'var(--success)', fontWeight: 'bold' }}>{osintData.reputation}</span>
                  </div>
                  <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
                    Flagged by {osintData.vendors_flagged} / {osintData.total_vendors} security vendors
                  </div>
                  {osintTags.length > 0 && (
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                      {osintTags.map(t => (
                        <span key={t} style={{ background: '#ef444422', color: '#ef4444', padding: '0.1rem 0.4rem', borderRadius: '4px', fontSize: '0.75rem' }}>{t}</span>
                      ))}
                    </div>
                  )}
                </div>
              )}
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
        {role !== 'READ_ONLY' && (
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
        )}
      </div>
    </div>
  );
};

export default EventDrillDownModal;

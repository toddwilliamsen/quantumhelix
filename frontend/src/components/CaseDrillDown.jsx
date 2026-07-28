import React, { useState, useEffect } from 'react';
import { X, MessageSquare, Briefcase } from 'lucide-react';
import toast from 'react-hot-toast';
import { apiFetch } from '../api';
import { useFocusTrap } from '../hooks/useFocusTrap';

const CaseDrillDown = ({ caseObj, onClose, token, readOnly = false }) => {
  const dialogRef = useFocusTrap(true);
  const [alerts, setAlerts] = useState([]);
  const [comments, setComments] = useState([]);
  const [newComment, setNewComment] = useState('');
  const [users, setUsers] = useState([]);
  const [status, setStatus] = useState(caseObj.status);
  const [assignee, setAssignee] = useState(caseObj.assignee_id || '');
  const [peak, setPeak] = useState(() => { try { return JSON.parse(caseObj.peak_framework || '[]'); } catch { return []; } });
  const [killChain, setKillChain] = useState(() => { try { return JSON.parse(caseObj.kill_chain || '[]'); } catch { return []; } });
  const [diamondModel, setDiamondModel] = useState(() => { try { return JSON.parse(caseObj.diamond_model || '[]'); } catch { return []; } });

  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      try {
        const [a, c, u] = await Promise.all([
          apiFetch(`/api/cases/${caseObj.id}/alerts`, { token, signal: controller.signal }),
          apiFetch(`/api/cases/${caseObj.id}/comments`, { token, signal: controller.signal }),
          apiFetch('/api/users', { token, signal: controller.signal }).catch(() => []),
        ]);
        setAlerts(a);
        setComments(c);
        setUsers(u);
      } catch (e) {
        if (e.name !== 'AbortError') toast.error('Failed to load case details');
      }
    };
    load();
    return () => controller.abort();
  }, [caseObj.id, token]);

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const fetchComments = async () => {
    try {
      setComments(await apiFetch(`/api/cases/${caseObj.id}/comments`, { token }));
    } catch { /* ignore */ }
  };

  const addComment = async (e) => {
    e.preventDefault();
    if (!newComment.trim()) return;
    try {
      await apiFetch(`/api/cases/${caseObj.id}/comments`, {
        method: 'POST',
        token,
        json: { content: newComment },
      });
      setNewComment('');
      fetchComments();
    } catch {
      toast.error('Failed to add comment');
    }
  };

  const unlinkAlert = async (alertId) => {
    try {
      await apiFetch(`/api/cases/${caseObj.id}/alerts/${alertId}`, { method: 'DELETE', token });
      setAlerts(prev => prev.filter(a => a.id !== alertId));
      toast.success('Alert unlinked');
    } catch {
      toast.error('Failed to unlink alert');
    }
  };

  const toggleFramework = (framework, value, setter) => {
    let newArr = [...framework];
    if (newArr.includes(value)) newArr = newArr.filter(v => v !== value);
    else newArr.push(value);
    setter(newArr);
    return newArr;
  };

  const updateCase = async (payload) => {
    try {
      await apiFetch(`/api/cases/${caseObj.id}`, {
        method: 'PUT',
        token,
        json: payload,
      });
      toast.success("Case updated", { id: `case-update-${caseObj.id}` });
    } catch {
      toast.error('Failed to update case');
    }
  };

  return (
    <div
      role="presentation"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}
    >
      <div
        ref={dialogRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby="case-dialog-title"
        style={{ background: 'var(--bg-color)', borderRadius: '12px', width: '90%', maxWidth: '1000px', maxHeight: '90vh', display: 'flex', flexDirection: 'column', overflow: 'hidden', outline: 'none' }}
      >
        <div style={{ padding: '1.5rem', borderBottom: '1px solid var(--border-color)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h2 id="case-dialog-title" style={{ margin: '0 0 0.5rem 0', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Briefcase size={24} /> CASE-{caseObj.id.toString().padStart(4, '0')}: {caseObj.title}
            </h2>
            <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Priority: {caseObj.priority} • Created: {new Date(caseObj.created_at).toLocaleString()}</div>
          </div>
          <button onClick={onClose} className="btn btn-secondary" aria-label="Close case details"><X size={20} /></button>
        </div>

        <div className="case-modal-columns" style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
          <div className="case-modal-primary" style={{ flex: 2, padding: '1.5rem', overflowY: 'auto', borderRight: '1px solid var(--border-color)' }}>
            <h3>Correlated Incident Cluster ({alerts.length} Alerts)</h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Alerts linked to this case. Unlink to remove from the cluster.</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '1rem' }}>
              {alerts.map(a => (
                <div key={a.id} style={{ padding: '1rem', background: 'var(--bg-primary)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <strong>{a.attack_phase}</strong>
                    <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                      <span style={{ color: '#ef4444' }}>Score: {a.score.toFixed(3)}</span>
                      {!readOnly && <button type="button" className="btn btn-secondary" style={{ padding: '0.2rem 0.5rem', fontSize: '0.75rem' }} onClick={() => unlinkAlert(a.id)}>Unlink</button>}
                    </div>
                  </div>
                  <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '0.5rem' }}>{a.plain_english}</div>
                </div>
              ))}
              {alerts.length === 0 && <div style={{ color: 'var(--text-secondary)' }}>No alerts linked to this case yet. Link from Triage Inbox.</div>}
            </div>
          </div>

          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: 'var(--surface)' }}>
            <div style={{ padding: '1.5rem', borderBottom: '1px solid var(--border-color)' }}>
              <h3 style={{ marginTop: 0 }}>Workflow</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <div>
                  <label style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.25rem' }}>Status</label>
                  <select className="form-control" value={status} disabled={readOnly} onChange={e => { setStatus(e.target.value); updateCase({ status: e.target.value }); }}>
                    <option value="Open">Open</option>
                    <option value="Pending">Pending (Waiting on User)</option>
                    <option value="Resolved">Resolved</option>
                  </select>
                </div>
                <div>
                  <label style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.25rem' }}>Assignee</label>
                  <select className="form-control" value={assignee} disabled={readOnly} onChange={e => { setAssignee(e.target.value); updateCase({ assignee_id: e.target.value }); }}>
                    <option value="">Unassigned</option>
                    {users.map(u => <option key={u.id} value={u.id}>{u.username}</option>)}
                  </select>
                </div>
              </div>
            </div>

            <div style={{ padding: '1.5rem', borderBottom: '1px solid var(--border-color)' }}>
              <h3 style={{ marginTop: 0 }}>Threat Frameworks</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', fontSize: '0.85rem' }}>
                <div>
                  <strong>PEAK</strong>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', marginTop: '0.5rem' }}>
                    {['Prepare', 'Execute', 'Analyze', 'Act'].map(f => (
                      <label key={f} style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                        <input type="checkbox" checked={peak.includes(f)} disabled={readOnly} onChange={() => { const n = toggleFramework(peak, f, setPeak); updateCase({ peak_framework: JSON.stringify(n) }); }} /> {f}
                      </label>
                    ))}
                  </div>
                </div>
                <div>
                  <strong>Cyber Kill Chain</strong>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', marginTop: '0.5rem' }}>
                    {['Reconnaissance', 'Weaponization', 'Delivery', 'Exploitation', 'Installation', 'C2', 'Actions on Objectives'].map(f => (
                      <label key={f} style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                        <input type="checkbox" checked={killChain.includes(f)} disabled={readOnly} onChange={() => { const n = toggleFramework(killChain, f, setKillChain); updateCase({ kill_chain: JSON.stringify(n) }); }} /> {f}
                      </label>
                    ))}
                  </div>
                </div>
                <div>
                  <strong>Diamond Model</strong>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', marginTop: '0.5rem' }}>
                    {['Adversary', 'Capability', 'Infrastructure', 'Victim'].map(f => (
                      <label key={f} style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                        <input type="checkbox" checked={diamondModel.includes(f)} disabled={readOnly} onChange={() => { const n = toggleFramework(diamondModel, f, setDiamondModel); updateCase({ diamond_model: JSON.stringify(n) }); }} /> {f}
                      </label>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            <div style={{ flex: 1, padding: '1.5rem', overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
              <h3 style={{ marginTop: 0 }}>Comments & Evidence</h3>
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '1rem', marginBottom: '1rem' }}>
                {comments.map(c => (
                  <div key={c.id} style={{ padding: '0.75rem', background: 'var(--bg-primary)', borderRadius: '8px' }}>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>{c.username} • {new Date(c.created_at).toLocaleString()}</div>
                    <div style={{ fontSize: '0.85rem' }}>{c.content}</div>
                  </div>
                ))}
              </div>
              {!readOnly && <form onSubmit={addComment} style={{ display: 'flex', gap: '0.5rem', marginTop: 'auto' }}>
                <input type="text" className="form-control" placeholder="Add a comment..." value={newComment} onChange={e => setNewComment(e.target.value)} style={{ flex: 1 }} aria-label="New comment" />
                <button type="submit" className="btn btn-primary" aria-label="Post comment"><MessageSquare size={16} /></button>
              </form>}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CaseDrillDown;

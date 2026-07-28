import React, { useState, useEffect } from 'react';
import { X, User as UserIcon, MessageSquare, Briefcase, Activity } from 'lucide-react';
import toast from 'react-hot-toast';

const CaseDrillDown = ({ caseObj, onClose, token }) => {
  const [alerts, setAlerts] = useState([]);
  const [comments, setComments] = useState([]);
  const [newComment, setNewComment] = useState('');
  const [users, setUsers] = useState([]);
  const [status, setStatus] = useState(caseObj.status);
  const [assignee, setAssignee] = useState(caseObj.assignee_id || '');

  useEffect(() => {
    fetchAlerts();
    fetchComments();
    fetchUsers();
  }, []);

  const fetchAlerts = async () => {
    try {
      const res = await fetch(`/api/cases/${caseObj.id}/alerts`, { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) setAlerts(await res.json());
    } catch(e) {}
  };

  const fetchComments = async () => {
    try {
      const res = await fetch(`/api/cases/${caseObj.id}/comments`, { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) setComments(await res.json());
    } catch(e) {}
  };

  const fetchUsers = async () => {
    try {
      const res = await fetch('/api/users', { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) {
        const u = await res.json();
        setUsers(u);
      }
    } catch(e) {}
  };

  const addComment = async (e) => {
    e.preventDefault();
    if (!newComment.trim()) return;
    try {
      const res = await fetch(`/api/cases/${caseObj.id}/comments`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ content: newComment })
      });
      if (res.ok) {
        setNewComment('');
        fetchComments();
      }
    } catch(e) {}
  };

  const updateCase = async (payload) => {
    try {
      const res = await fetch(`/api/cases/${caseObj.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify(payload)
      });
      if (res.ok) toast.success("Case updated");
    } catch(e) {}
  };

  return (
    <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
      <div style={{ background: 'var(--bg-color)', borderRadius: '12px', width: '90%', maxWidth: '1000px', maxHeight: '90vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        
        {/* Header */}
        <div style={{ padding: '1.5rem', borderBottom: '1px solid var(--border-color)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h2 style={{ margin: '0 0 0.5rem 0', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Briefcase size={24} /> CASE-{caseObj.id.toString().padStart(4, '0')}: {caseObj.title}
            </h2>
            <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Priority: {caseObj.priority} • Created: {new Date(caseObj.created_at).toLocaleString()}</div>
          </div>
          <button onClick={onClose} className="btn btn-secondary"><X size={20} /></button>
        </div>

        <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
          {/* Main Content */}
          <div style={{ flex: 2, padding: '1.5rem', overflowY: 'auto', borderRight: '1px solid var(--border-color)' }}>
            <h3>Correlated Incident Cluster ({alerts.length} Alerts)</h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Alerts dynamically grouped by the Quantum Correlation Engine.</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '1rem' }}>
              {alerts.map(a => (
                <div key={a.id} style={{ padding: '1rem', background: 'var(--bg-primary)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <strong>{a.attack_phase}</strong>
                    <span style={{ color: '#ef4444' }}>Score: {a.score.toFixed(3)}</span>
                  </div>
                  <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '0.5rem' }}>{a.plain_english}</div>
                </div>
              ))}
              {alerts.length === 0 && <div style={{ color: 'var(--text-secondary)' }}>No alerts linked to this case yet.</div>}
            </div>
          </div>

          {/* Sidebar */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: 'var(--surface)' }}>
            
            <div style={{ padding: '1.5rem', borderBottom: '1px solid var(--border-color)' }}>
              <h3 style={{ marginTop: 0 }}>Workflow</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <div>
                  <label style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.25rem' }}>Status</label>
                  <select className="form-control" value={status} onChange={e => { setStatus(e.target.value); updateCase({ status: e.target.value }); }}>
                    <option value="Open">Open</option>
                    <option value="Pending">Pending (Waiting on User)</option>
                    <option value="Resolved">Resolved</option>
                  </select>
                </div>
                <div>
                  <label style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.25rem' }}>Assignee</label>
                  <select className="form-control" value={assignee} onChange={e => { setAssignee(e.target.value); updateCase({ assignee_id: e.target.value }); }}>
                    <option value="">Unassigned</option>
                    {users.map(u => <option key={u.id} value={u.id}>{u.username}</option>)}
                  </select>
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
              <form onSubmit={addComment} style={{ display: 'flex', gap: '0.5rem', marginTop: 'auto' }}>
                <input type="text" className="form-control" placeholder="Add a comment..." value={newComment} onChange={e => setNewComment(e.target.value)} style={{ flex: 1 }} />
                <button type="submit" className="btn btn-primary"><MessageSquare size={16} /></button>
              </form>
            </div>

          </div>
        </div>
      </div>
    </div>
  );
};

export default CaseDrillDown;

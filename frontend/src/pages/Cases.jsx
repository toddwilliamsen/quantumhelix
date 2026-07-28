import React, { useState, useEffect } from 'react';
import { Briefcase, AlertTriangle, Search, Activity, User as UserIcon } from 'lucide-react';
import CaseDrillDown from '../components/CaseDrillDown';
import toast from 'react-hot-toast';

function Cases({ token }) {
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [selectedCase, setSelectedCase] = useState(null);
  
  useEffect(() => {
    fetchCases();
  }, []);

  const fetchCases = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/cases', { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) setCases(await res.json());
    } catch(e) { console.error(e); }
    setLoading(false);
  };

  const createCase = async (e) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    try {
      const res = await fetch('/api/cases', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ title: newTitle, priority: 'High' })
      });
      if (res.ok) {
        toast.success("Case created");
        setNewTitle('');
        fetchCases();
      }
    } catch(e) { toast.error("Failed to create case"); }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
      <div className="page-header">
        <h1 className="page-title">Case Management</h1>
        <p className="page-subtitle">Track, assign, and resolve correlated incident clusters.</p>
      </div>

      <div className="card" style={{ maxWidth: '1000px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
          <form onSubmit={createCase} style={{ display: 'flex', gap: '0.5rem', width: '400px' }}>
            <input 
              type="text" 
              value={newTitle} 
              onChange={e => setNewTitle(e.target.value)} 
              placeholder="e.g. Possible Data Exfiltration via S3" 
              className="form-control" 
              style={{ flex: 1, padding: '0.5rem', borderRadius: '4px', border: '1px solid var(--border-color)', background: 'var(--bg-color)', color: 'white' }}
            />
            <button type="submit" className="btn btn-primary">Open Case</button>
          </form>
          <button className="btn btn-secondary" onClick={fetchCases}>Refresh</button>
        </div>

        <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '2px solid var(--border-color)' }}>
              <th style={{ padding: '0.75rem 0' }}>Case ID</th>
              <th style={{ padding: '0.75rem 0' }}>Title</th>
              <th style={{ padding: '0.75rem 0' }}>Priority</th>
              <th style={{ padding: '0.75rem 0' }}>Status</th>
              <th style={{ padding: '0.75rem 0' }}>Created</th>
            </tr>
          </thead>
          <tbody>
            {cases.map(c => (
              <tr key={c.id} onClick={() => setSelectedCase(c)} style={{ borderBottom: '1px solid var(--border-color)', cursor: 'pointer' }} className="hover-bg">
                <td style={{ padding: '1rem 0', fontFamily: 'monospace', color: 'var(--text-secondary)' }}>CASE-{c.id.toString().padStart(4, '0')}</td>
                <td style={{ padding: '1rem 0', fontWeight: 'bold' }}>{c.title}</td>
                <td style={{ padding: '1rem 0' }}>
                  <span style={{ color: c.priority === 'High' ? '#ef4444' : '#f59e0b', fontWeight: 'bold' }}>{c.priority}</span>
                </td>
                <td style={{ padding: '1rem 0' }}>
                  <span style={{ background: 'var(--bg-primary)', padding: '0.2rem 0.5rem', borderRadius: '4px', fontSize: '0.85rem' }}>{c.status}</span>
                </td>
                <td style={{ padding: '1rem 0', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>{new Date(c.created_at).toLocaleDateString()}</td>
              </tr>
            ))}
            {cases.length === 0 && !loading && (
              <tr><td colSpan="5" style={{ padding: '2rem 0', textAlign: 'center', color: 'var(--text-secondary)' }}>No active cases found.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {selectedCase && (
        <CaseDrillDown 
          caseObj={selectedCase} 
          token={token} 
          onClose={() => { setSelectedCase(null); fetchCases(); }} 
        />
      )}
    </div>
  );
}

export default Cases;

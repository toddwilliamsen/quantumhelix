import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import CaseDrillDown from '../components/CaseDrillDown';
import toast from 'react-hot-toast';

function Cases({ token }) {
  const readOnly = localStorage.getItem('quantum_role') === 'READ_ONLY';
  const isMspAdmin = localStorage.getItem('quantum_role') === 'SUPER_ADMIN';
  const [searchParams, setSearchParams] = useSearchParams();
  const caseIdParam = searchParams.get('caseId');
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newPriority, setNewPriority] = useState('Medium');
  const [selectedCase, setSelectedCase] = useState(null);

  const casesUrl = isMspAdmin ? '/api/cases?scope=all' : '/api/cases';
  
  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      setLoading(true);
      try {
        const res = await fetch(casesUrl, {
          headers: { 'Authorization': `Bearer ${token}` },
          signal: controller.signal,
        });
        if (res.ok) {
          const data = await res.json();
          setCases(data);
          if (caseIdParam) {
            const match = data.find(c => String(c.id) === String(caseIdParam));
            if (match) setSelectedCase(match);
          }
        } else toast.error('Failed to load cases');
      } catch (e) {
        if (e.name !== 'AbortError') console.error(e);
      } finally {
        setLoading(false);
      }
    })();
    return () => controller.abort();
  }, [token, caseIdParam, casesUrl]);

  const fetchCases = async () => {
    setLoading(true);
    try {
      const res = await fetch(casesUrl, { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) setCases(await res.json());
      else toast.error('Failed to load cases');
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
        body: JSON.stringify({ title: newTitle, priority: newPriority })
      });
      if (res.ok) {
        toast.success("Case created");
        setNewTitle('');
        fetchCases();
      } else {
        toast.error("Failed to create case");
      }
    } catch { toast.error("Failed to create case"); }
  };

  const closeCase = () => {
    setSelectedCase(null);
    if (caseIdParam) {
      searchParams.delete('caseId');
      setSearchParams(searchParams, { replace: true });
    }
    fetchCases();
  };

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Cases</h1>
        <p className="page-subtitle">Coordinate investigation, ownership, evidence, and resolution.</p>
      </div>

      <div className="card">
        <div className="toolbar">
          {!readOnly && <form onSubmit={createCase} className="toolbar-group">
            <label htmlFor="case-title" className="control-label">New case</label>
            <input 
              id="case-title"
              type="text" 
              value={newTitle} 
              onChange={e => setNewTitle(e.target.value)} 
              placeholder="Investigation title"
              className="form-control" 
            />
            <select
              className="form-control"
              value={newPriority}
              onChange={e => setNewPriority(e.target.value)}
              aria-label="Case priority"
            >
              <option value="Low">Low</option>
              <option value="Medium">Medium</option>
              <option value="High">High</option>
              <option value="Critical">Critical</option>
            </select>
            <button type="submit" className="btn btn-primary" disabled={!newTitle.trim()}>Create case</button>
          </form>}
          <button className="btn btn-secondary" onClick={fetchCases} disabled={loading}>
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>

        {loading && cases.length === 0 ? (
          <p style={{ color: 'var(--text-secondary)' }}>Loading cases…</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Case</th>
                  <th>Tenant</th>
                  <th>Title</th>
                  <th>Priority</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {cases.map(c => (
                  <tr key={c.id}>
                    <td style={{ fontFamily: 'monospace', color: 'var(--text-secondary)' }}>CASE-{c.id.toString().padStart(4, '0')}</td>
                    <td>
                      <span className="tenant-chip">{c.tenant_name || `Tenant ${c.tenant_id}`}</span>
                    </td>
                    <td style={{ fontWeight: 600 }}>{c.title}</td>
                    <td>
                      <span className={`status-pill ${c.priority === 'High' ? 'is-danger' : ''}`}>{c.priority}</span>
                    </td>
                    <td><span className="status-pill">{c.status}</span></td>
                    <td style={{ color: 'var(--text-secondary)' }}>{new Date(c.created_at).toLocaleDateString()}</td>
                    <td style={{ textAlign: 'right' }}>
                      <button className="btn btn-secondary" onClick={() => setSelectedCase(c)}>Open</button>
                    </td>
                  </tr>
                ))}
                {cases.length === 0 && !loading && (
                  <tr><td colSpan="7" style={{ padding: '32px', textAlign: 'center', color: 'var(--text-secondary)' }}>No cases have been created.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selectedCase && (
        <CaseDrillDown 
          caseObj={selectedCase} 
          token={token} 
          readOnly={readOnly}
          onClose={closeCase} 
        />
      )}
    </div>
  );
}

export default Cases;

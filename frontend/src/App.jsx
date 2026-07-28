import React, { useState, useEffect } from 'react';
import { Routes, Route, NavLink, useNavigate } from 'react-router-dom';
import { LayoutDashboard, Inbox, BarChart2, Play, Pause, Trash2, Activity, LogOut, Settings as SettingsIcon, Moon, Sun, Map, Zap, Briefcase } from 'lucide-react';
import { Toaster, toast } from 'react-hot-toast';
import Dashboard from './pages/Dashboard';
import TriageInbox from './pages/TriageInbox';
import Analytics from './pages/Analytics';
import Settings from './pages/Settings';
import Login from './pages/Login';
import ThreatMap from './pages/ThreatMap';
import Playground from './pages/Playground';
import Cases from './pages/Cases';

function App() {
  const [token, setToken] = useState(localStorage.getItem('quantum_token'));
  const [role, setRole] = useState(localStorage.getItem('quantum_role'));
  const [username, setUsername] = useState(localStorage.getItem('quantum_username'));
  const navigate = useNavigate();

  const [state, setState] = useState({
    streaming: false,
    history: [],
    processed: 0,
    open_alerts: 0,
    threshold: 0.68,
  });

  const [theme, setTheme] = useState(localStorage.getItem('theme') || 'light');

  useEffect(() => {
    document.body.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  }, [theme]);

  const [localThreshold, setLocalThreshold] = useState(state.threshold);

  useEffect(() => {
    setLocalThreshold(state.threshold);
  }, [state.threshold]);

  const handleLogin = (newToken, newRole, newUsername) => {
    localStorage.setItem('quantum_token', newToken);
    localStorage.setItem('quantum_role', newRole);
    localStorage.setItem('quantum_username', newUsername);
    setToken(newToken);
    setRole(newRole);
    setUsername(newUsername);
  };

  const handleLogout = () => {
    localStorage.removeItem('quantum_token');
    localStorage.removeItem('quantum_role');
    localStorage.removeItem('quantum_username');
    setToken(null);
    setRole(null);
    setUsername(null);
    navigate('/');
  };

  useEffect(() => {
    if (!token) return;

    const eventSource = new EventSource(`/api/stream?token=${token}`);
    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'state') {
        setState(data);
      }
    };
    return () => eventSource.close();
  }, [token]);

  const updateControls = async (updates) => {
    try {
      await fetch('/api/controls', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(updates),
      });
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    if (!token) return;
    let timeout;
    const resetIdleTimer = () => {
      clearTimeout(timeout);
      timeout = setTimeout(() => {
        if (state.streaming) {
          updateControls({ streaming: false });
          toast('Stream auto-paused due to 3 minutes of inactivity.', { icon: '⏸️' });
        }
      }, 3 * 60 * 1000);
    };

    window.addEventListener('mousemove', resetIdleTimer);
    window.addEventListener('mousedown', resetIdleTimer);
    window.addEventListener('keydown', resetIdleTimer);
    window.addEventListener('scroll', resetIdleTimer, true);

    resetIdleTimer();

    return () => {
      clearTimeout(timeout);
      window.removeEventListener('mousemove', resetIdleTimer);
      window.removeEventListener('mousedown', resetIdleTimer);
      window.removeEventListener('keydown', resetIdleTimer);
      window.removeEventListener('scroll', resetIdleTimer, true);
    };
  }, [token, state.streaming]);

  if (!token) {
    return <Login onLogin={handleLogin} />;
  }

  return (
    <div className="app-container">
      <Toaster position="top-right" />
      <aside className="sidebar">
        <div className="brand" style={{ marginBottom: '1rem' }}>
          <Activity color="#2563eb" />
          Quantum Helix
        </div>
        <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '2rem', display: 'flex', justifyContent: 'space-between' }}>
          <span>Logged in as <strong>{username}</strong></span>
          <span style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.25rem' }} onClick={handleLogout}>
            <LogOut size={12} /> Logout
          </span>
        </div>

        <nav className="nav-links">
          <NavLink to="/" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <LayoutDashboard size={20} /> Dashboard
          </NavLink>
          <NavLink to="/triage" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <Inbox size={20} /> Triage Inbox
            {state.open_alerts > 0 && (
              <span style={{ marginLeft: 'auto', background: '#ef4444', color: 'white', borderRadius: '999px', padding: '0.1rem 0.5rem', fontSize: '0.75rem' }}>
                {state.open_alerts}
              </span>
            )}
          </NavLink>
          <NavLink to="/analytics" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <BarChart2 size={20} /> Analytics & Models
          </NavLink>
                    <NavLink to="/cases" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <Briefcase size={20} /> Case Management
          </NavLink>
          <NavLink to="/threat-map" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <Map size={20} /> Threat Map
          </NavLink>
          <NavLink to="/playground" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <Zap size={20} /> Model Playground
          </NavLink>
          {role === 'SUPER_ADMIN' || role === 'TENANT_ADMIN' && (
            <NavLink to="/settings" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              <SettingsIcon size={20} /> Settings & Rules
            </NavLink>
          )}
        </nav>

        {role === 'SUPER_ADMIN' || role === 'TENANT_ADMIN' && (
          <div className="controls-section" style={{ marginTop: 'auto' }}>
            <div className="control-group">
              <span className="control-label">Alert Sensitivity ({localThreshold.toFixed(2)})</span>
              <input 
                type="range" 
                min="0.40" max="0.90" step="0.01" 
                value={localThreshold}
                onChange={(e) => setLocalThreshold(parseFloat(e.target.value))}
                onMouseUp={() => updateControls({ threshold: localThreshold })}
                onTouchEnd={() => updateControls({ threshold: localThreshold })}
                style={{ cursor: 'pointer' }}
              />
            </div>

            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
              {!state.streaming ? (
                <button className="btn btn-primary" style={{ flex: 1 }} onClick={() => updateControls({ streaming: true })}>
                  <Play size={16} /> Start
                </button>
              ) : (
                <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => updateControls({ streaming: false })}>
                  <Pause size={16} /> Pause
                </button>
              )}
              <button className="btn btn-secondary" onClick={() => updateControls({ clear: true })}>
                <Trash2 size={16} />
              </button>
            </div>
            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
              <button 
                className="btn btn-secondary" 
                style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }} 
                onClick={() => setTheme(t => t === 'light' ? 'dark' : 'light')}
              >
                {theme === 'light' ? <><Moon size={16} /> Dark Mode</> : <><Sun size={16} /> Light Mode</>}
              </button>
            </div>
          </div>
        )}
      </aside>

      <main className="main-content">
        <Routes>
          <Route path="/" element={<Dashboard state={state} />} />
          <Route path="/triage" element={<TriageInbox state={state} token={token} />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/cases" element={<Cases token={token} />} />
          <Route path="/threat-map" element={<ThreatMap token={token} />} />
          <Route path="/playground" element={<Playground token={token} />} />
          <Route path="/settings" element={<Settings token={token} />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;

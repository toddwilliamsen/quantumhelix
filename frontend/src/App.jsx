import React, { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react';
import { Routes, Route, NavLink, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { LayoutDashboard, Inbox, BarChart2, Play, Pause, Trash2, Activity, LogOut, Settings as SettingsIcon, Moon, Sun, Map, Zap, Briefcase, UserCog } from 'lucide-react';
import { Toaster, toast } from 'react-hot-toast';
import Login from './pages/Login';
import { isAdmin } from './roles';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const TriageInbox = lazy(() => import('./pages/TriageInbox'));
const Analytics = lazy(() => import('./pages/Analytics'));
const Settings = lazy(() => import('./pages/Settings'));
const ThreatMap = lazy(() => import('./pages/ThreatMap'));
const Playground = lazy(() => import('./pages/Playground'));
const Cases = lazy(() => import('./pages/Cases'));
const Account = lazy(() => import('./pages/Account'));

function App() {
  const [token, setToken] = useState(localStorage.getItem('quantum_token'));
  const [role, setRole] = useState(localStorage.getItem('quantum_role'));
  const [username, setUsername] = useState(localStorage.getItem('quantum_username'));
  const [mustChangePassword, setMustChangePassword] = useState(
    localStorage.getItem('quantum_must_change_password') === '1'
  );
  const navigate = useNavigate();
  const location = useLocation();
  const prevOpenAlerts = useRef(null);
  const pathRef = useRef(location.pathname);
  pathRef.current = location.pathname;

  const [state, setState] = useState({
    streaming: false,
    history: [],
    processed: 0,
    open_alerts: 0,
    threshold: 0.68,
  });

  const [theme, setTheme] = useState(localStorage.getItem('theme') || 'light');

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    document.body.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  }, [theme]);

  const [localThreshold, setLocalThreshold] = useState(state.threshold);

  useEffect(() => {
    setLocalThreshold(state.threshold);
  }, [state.threshold]);

  const handleLogin = (newToken, newRole, newUsername, requirePasswordChange = false) => {
    localStorage.setItem('quantum_token', newToken);
    localStorage.setItem('quantum_role', newRole);
    localStorage.setItem('quantum_username', newUsername);
    if (requirePasswordChange) {
      localStorage.setItem('quantum_must_change_password', '1');
    } else {
      localStorage.removeItem('quantum_must_change_password');
    }
    setToken(newToken);
    setRole(newRole);
    setUsername(newUsername);
    setMustChangePassword(!!requirePasswordChange);
    if (requirePasswordChange) {
      navigate('/account');
    }
  };

  const handleLogout = useCallback(() => {
    localStorage.removeItem('quantum_token');
    localStorage.removeItem('quantum_role');
    localStorage.removeItem('quantum_username');
    localStorage.removeItem('quantum_must_change_password');
    setToken(null);
    setRole(null);
    setUsername(null);
    setMustChangePassword(false);
    navigate('/');
  }, [navigate]);

  useEffect(() => {
    const onToken = (e) => {
      if (e.detail) setToken(e.detail);
      setMustChangePassword(false);
    };
    window.addEventListener('quantum:token', onToken);
    return () => window.removeEventListener('quantum:token', onToken);
  }, []);

  useEffect(() => {
    if (!token || !mustChangePassword) return;
    if (location.pathname !== '/account') {
      navigate('/account', { replace: true });
      toast('Change your password before continuing.');
    }
  }, [token, mustChangePassword, location.pathname, navigate]);

  const [streamStatus, setStreamStatus] = useState('connecting'); // connecting | live | reconnecting

  useEffect(() => {
    if (!token) return;
    let eventSource;
    let cancelled = false;
    let reconnectTimer;

    const connect = async () => {
      try {
        if (!cancelled) setStreamStatus((s) => (s === 'live' ? 'reconnecting' : 'connecting'));
        const res = await fetch('/api/stream/ticket', {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.status === 401 || res.status === 403) {
          // Session revoked or account deactivated by an administrator.
          const data = await res.json().catch(() => ({}));
          toast.error(data.message || 'Your session has ended. Please sign in again.');
          handleLogout();
          return;
        }
        if (!res.ok) throw new Error('stream ticket failed');
        const { token: ticket } = await res.json();
        if (cancelled) return;
        eventSource = new EventSource(`/api/stream?token=${encodeURIComponent(ticket)}`);
        eventSource.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.type === 'state') {
              const nextOpen = data.open_alerts ?? 0;
              if (
                prevOpenAlerts.current !== null
                && nextOpen > prevOpenAlerts.current
                && pathRef.current !== '/triage'
              ) {
                const delta = nextOpen - prevOpenAlerts.current;
                toast(
                  (t) => (
                    <span>
                      {delta === 1 ? 'New open alert' : `${delta} new open alerts`}{' '}
                      <button
                        type="button"
                        className="link-button"
                        onClick={() => { toast.dismiss(t.id); navigate('/triage'); }}
                        style={{ marginLeft: '0.35rem' }}
                      >
                        Open triage
                      </button>
                    </span>
                  ),
                  { id: 'new-alerts', duration: 6000 }
                );
              }
              prevOpenAlerts.current = nextOpen;
              setState(data);
              setStreamStatus('live');
            }
          } catch (e) {
            console.error('Invalid SSE payload', e);
          }
        };
        eventSource.onerror = () => {
          setStreamStatus('reconnecting');
          eventSource.close();
          if (!cancelled) {
            clearTimeout(reconnectTimer);
            reconnectTimer = setTimeout(connect, 1500);
          }
        };
      } catch (e) {
        console.error(e);
        setStreamStatus('reconnecting');
        if (!cancelled) {
          clearTimeout(reconnectTimer);
          reconnectTimer = setTimeout(connect, 3000);
        }
      }
    };

    connect();
    return () => {
      cancelled = true;
      clearTimeout(reconnectTimer);
      if (eventSource) eventSource.close();
    };
  }, [token, handleLogout]);

  const updateControls = useCallback(async (updates) => {
    try {
      const res = await fetch('/api/controls', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(updates),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.message || 'Control update failed');
      }
    } catch (e) {
      console.error(e);
      toast.error(e.message || 'Unable to update stream controls');
    }
  }, [token]);

  const clearEvents = () => {
    if (window.confirm('Clear event history and alerts for this tenant? This cannot be undone.')) {
      updateControls({ clear: true });
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
          toast('Stream paused after 3 minutes of inactivity.');
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
  }, [token, state.streaming, updateControls]);

  if (!token) {
    return <Login onLogin={handleLogin} />;
  }

  return (
    <div className="app-container">
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: 'var(--surface)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border-color)',
          },
        }}
      />
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark"><Activity size={18} /></span>
          <span className="brand-copy">
            <span className="brand-name">Quantum Helix</span>
            <span className="brand-product">Security operations</span>
          </span>
        </div>

        <div className="sidebar-session">
          <span>Signed in as <strong>{username}</strong></span>
          <button type="button" onClick={handleLogout} aria-label="Log out" className="link-button">
            <LogOut size={12} /> Logout
          </button>
        </div>

        <div className="nav-section-label">Investigate</div>
        <nav className="nav-links" aria-label="Primary">
          <NavLink to="/" end className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <LayoutDashboard size={18} /> Overview
          </NavLink>
          <NavLink to="/triage" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <Inbox size={18} /> Triage
            {state.open_alerts > 0 && (
              <span className="nav-badge">{state.open_alerts}</span>
            )}
          </NavLink>
          <NavLink to="/cases" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <Briefcase size={18} /> Cases
          </NavLink>
          <NavLink to="/threat-map" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <Map size={18} /> Threat map
          </NavLink>
        </nav>

        <div className="nav-section-label">Analyze</div>
        <nav className="nav-links" aria-label="Analytics">
          <NavLink to="/analytics" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <BarChart2 size={18} /> Analytics
          </NavLink>
          {isAdmin(role) && (
            <NavLink to="/playground" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              <Zap size={18} /> Model controls
            </NavLink>
          )}
        </nav>

        <div className="nav-section-label">Account</div>
        <nav className="nav-links" aria-label="Account">
          <NavLink to="/account" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <UserCog size={18} /> My account
          </NavLink>
          {isAdmin(role) && (
            <NavLink to="/settings" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              <SettingsIcon size={18} /> Administration
            </NavLink>
          )}
        </nav>

        <div className="controls-section">
          {isAdmin(role) && (
            <>
              <div className="control-group">
                <label className="control-label" htmlFor="alert-threshold">
                  Alert threshold · {localThreshold.toFixed(2)}
                </label>
                <input
                  id="alert-threshold"
                  type="range"
                  min="0.40" max="0.90" step="0.01"
                  value={localThreshold}
                  onChange={(e) => setLocalThreshold(parseFloat(e.target.value))}
                  onMouseUp={() => updateControls({ threshold: localThreshold })}
                  onTouchEnd={() => updateControls({ threshold: localThreshold })}
                  onKeyUp={() => updateControls({ threshold: localThreshold })}
                  onBlur={() => updateControls({ threshold: localThreshold })}
                />
              </div>

              <div className="sidebar-actions">
                {!state.streaming ? (
                  <button className="btn btn-primary" onClick={() => updateControls({ streaming: true })}>
                    <Play size={15} /> Start
                  </button>
                ) : (
                  <button className="btn btn-secondary" onClick={() => updateControls({ streaming: false })}>
                    <Pause size={16} /> Pause
                  </button>
                )}
                <button className="btn btn-secondary btn-icon" onClick={clearEvents} aria-label="Clear event history">
                  <Trash2 size={16} />
                </button>
              </div>
            </>
          )}
        </div>
      </aside>

      <div className="workspace">
        <header className="workspace-topbar">
          <div className="workspace-topbar__status" aria-live="polite">
            <span
              aria-hidden
              className={`stream-indicator__dot ${
                streamStatus === 'live' ? 'is-live' : streamStatus === 'reconnecting' ? 'is-reconnecting' : ''
              }`}
            />
            <span>
              {streamStatus === 'live' ? 'Live feed connected' : streamStatus === 'reconnecting' ? 'Reconnecting…' : 'Connecting…'}
              {state.streaming ? ' · Monitoring' : ' · Paused'}
              {` · ${state.processed} events`}
            </span>
          </div>
          <div className="workspace-topbar__actions">
            <span style={{ color: 'var(--text-secondary)', fontSize: '0.78rem' }}>{role?.replace('_', ' ')}</span>
            <button
              className="btn btn-secondary"
              onClick={() => setTheme(t => t === 'light' ? 'dark' : 'light')}
              aria-label="Toggle theme"
            >
              {theme === 'light' ? <Moon size={15} /> : <Sun size={15} />}
            </button>
          </div>
        </header>

        <main className="main-content">
          <Suspense fallback={<div className="page-loading"><div className="spinner" /> Loading workspace…</div>}>
            <Routes>
              <Route path="/" element={<Dashboard state={state} token={token} />} />
              <Route path="/triage" element={<TriageInbox state={state} token={token} />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="/cases" element={<Cases token={token} />} />
              <Route path="/threat-map" element={<ThreatMap token={token} />} />
              <Route path="/playground" element={
                isAdmin(role) ? <Playground token={token} /> : <Navigate to="/" replace />
              } />
              <Route path="/account" element={<Account token={token} />} />
              <Route path="/settings" element={
                isAdmin(role)
                  ? <Settings token={token} />
                  : <Navigate to="/" replace />
              } />
            </Routes>
          </Suspense>
        </main>
      </div>
    </div>
  );
}

export default App;

import React, { useEffect, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import { useNavigate } from 'react-router-dom';
import {
  Activity, BellRing, ShieldCheck, Inbox, Briefcase, Map, BarChart2,
  Zap, Settings as SettingsIcon, ChevronRight, AlertTriangle, UserCog,
} from 'lucide-react';
import InfoBubble from '../components/InfoBubble';
import { apiFetch } from '../api';
import { isAdmin, ROLE_LABELS } from '../roles';

function DashTile({ icon: Icon, title, subtitle, meta, onClick, tone }) {
  return (
    <button type="button" className={`dash-tile ${tone ? `is-${tone}` : ''}`} onClick={onClick}>
      <span className="dash-tile__icon" aria-hidden>
        <Icon size={18} />
      </span>
      <span className="dash-tile__body">
        <span className="dash-tile__title">{title}</span>
        <span className="dash-tile__subtitle">{subtitle}</span>
        {meta != null && meta !== '' && <span className="dash-tile__meta">{meta}</span>}
      </span>
      <ChevronRight size={16} className="dash-tile__chevron" aria-hidden />
    </button>
  );
}

function MetricLink({ icon: Icon, label, value, hint, onClick, tone }) {
  return (
    <button
      type="button"
      className={`metric-card metric-card--link ${tone ? `is-${tone}` : ''}`}
      onClick={onClick}
      title={hint}
      aria-label={`${label}: ${value}. ${hint}`}
    >
      <div className="metric-label">
        <Icon size={14} /> {label}
      </div>
      <div className="metric-value">{value}</div>
      <div className="metric-card__cta">Open <ChevronRight size={14} /></div>
    </button>
  );
}

function Dashboard({ state, token }) {
  const navigate = useNavigate();
  const role = localStorage.getItem('quantum_role');
  const admin = isAdmin(role);

  const [recentAlerts, setRecentAlerts] = useState([]);
  const [cases, setCases] = useState([]);
  const [disagreements, setDisagreements] = useState([]);
  const [loadError, setLoadError] = useState(null);

  const highestRisk = state.history.length > 0
    ? Math.max(...state.history.map(h => h.ensemble)).toFixed(2)
    : '—';

  useEffect(() => {
    if (!token) return undefined;
    const controller = new AbortController();
    const { signal } = controller;

    Promise.all([
      apiFetch(`/api/alerts?status=open&limit=6${role === 'SUPER_ADMIN' ? '&scope=all' : ''}`, { token, signal }),
      apiFetch(`/api/cases${role === 'SUPER_ADMIN' ? '?scope=all' : ''}`, { token, signal }),
      apiFetch(`/api/analytics/overview${role === 'SUPER_ADMIN' ? '?scope=all' : ''}`, { token, signal }).catch(() => null),
    ])
      .then(([alertsRes, casesRes, overview]) => {
        setRecentAlerts(alertsRes.alerts || []);
        setCases(Array.isArray(casesRes) ? casesRes : []);
        setDisagreements(overview?.disagreements || []);
        setLoadError(null);
      })
      .catch((e) => {
        if (e.name !== 'AbortError') setLoadError(e.message || 'Failed to load dashboard');
      });

    return () => controller.abort();
  }, [token, state.open_alerts, state.processed]);

  const openCases = cases.filter(c => (c.status || '').toLowerCase() !== 'resolved');
  const criticalAlerts = recentAlerts.filter(a => a.severity === 'CRITICAL').length;

  const handleChartClick = (data) => {
    if (data?.activePayload?.[0]?.payload?.alert_id) {
      navigate(`/triage?alertId=${data.activePayload[0].payload.alert_id}`);
      return;
    }
    navigate('/triage');
  };

  return (
    <div className="dashboard-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Overview</h1>
          <p className="page-subtitle">
            Operations hub — jump into triage, cases, threat map, and analytics from live workload.
          </p>
        </div>
        <div className="page-actions">
          <span className="dash-role-pill">{ROLE_LABELS[role] || role}</span>
          {state.streaming ? (
            <span className="status-pill is-success">Monitoring</span>
          ) : (
            <span className="status-pill">Paused</span>
          )}
        </div>
      </div>

      {loadError && (
        <div className="form-error" role="alert" style={{ marginBottom: '1rem' }}>{loadError}</div>
      )}

      <div className="metrics-grid">
        <MetricLink
          icon={BellRing}
          label="Open alerts"
          value={state.open_alerts}
          hint="Alerts waiting in Triage. Click to open the queue."
          onClick={() => navigate('/triage')}
          tone={state.open_alerts > 0 ? 'danger' : undefined}
        />
        <MetricLink
          icon={Briefcase}
          label="Open cases"
          value={openCases.length}
          hint="Active investigation cases. Click to open Cases."
          onClick={() => navigate('/cases')}
        />
        <MetricLink
          icon={ShieldCheck}
          label="Peak risk"
          value={highestRisk}
          hint="Highest ensemble score in the live history window."
          onClick={() => navigate('/analytics')}
        />
        <MetricLink
          icon={Activity}
          label="Events analyzed"
          value={state.processed}
          hint="Events scored since history was cleared."
          onClick={() => navigate('/threat-map')}
        />
      </div>

      <section className="dash-section">
        <div className="dash-section__head">
          <h2>Workspace</h2>
          <p>Open any console surface</p>
        </div>
        <div className="dash-tile-grid">
          <DashTile
            icon={Inbox}
            title="Triage"
            subtitle="Claim, classify, and escalate alerts"
            meta={state.open_alerts ? `${state.open_alerts} open · ${criticalAlerts} critical in view` : 'Queue clear'}
            tone={state.open_alerts ? 'danger' : undefined}
            onClick={() => navigate('/triage')}
          />
          <DashTile
            icon={Briefcase}
            title="Cases"
            subtitle="Investigations, ownership, and notes"
            meta={`${openCases.length} open of ${cases.length} total`}
            onClick={() => navigate('/cases')}
          />
          <DashTile
            icon={Map}
            title="Threat map"
            subtitle="Identity progression across attack phases"
            meta="Kanban · 3D · globe"
            onClick={() => navigate('/threat-map')}
          />
          <DashTile
            icon={BarChart2}
            title="Analytics"
            subtitle="Feature space, disagreement, latency"
            meta={disagreements.length ? `${disagreements.length} disagreement alerts` : 'Model health'}
            onClick={() => navigate('/analytics')}
          />
          {admin && (
            <DashTile
              icon={Zap}
              title="Model controls"
              subtitle="Ensemble weights and latency profile"
              meta="Admin"
              onClick={() => navigate('/playground')}
            />
          )}
          {admin && (
            <DashTile
              icon={SettingsIcon}
              title="Administration"
              subtitle="Users, tenants, rules, playbooks"
              meta="Admin"
              onClick={() => navigate('/settings')}
            />
          )}
          <DashTile
            icon={UserCog}
            title="My account"
            subtitle="Password and MFA enrollment"
            onClick={() => navigate('/account')}
          />
        </div>
      </section>

      <div className="dash-split">
        <section className="card dash-panel">
          <div className="dash-panel__head">
            <h3>Needs attention</h3>
            <button type="button" className="link-button dash-panel__link" onClick={() => navigate('/triage')}>
              All triage
            </button>
          </div>
          {recentAlerts.length === 0 ? (
            <div className="empty-state" style={{ padding: '1.5rem 0.5rem' }}>
              <p>No open alerts. Start monitoring to populate the queue.</p>
            </div>
          ) : (
            <ul className="dash-list">
              {recentAlerts.map((a) => (
                <li key={a.id}>
                  <button
                    type="button"
                    className="dash-list__item"
                    onClick={() => navigate(`/triage?alertId=${a.id}`)}
                  >
                    <span className={`dash-sev is-${(a.severity || '').toLowerCase()}`}>{a.severity}</span>
                    <span className="dash-list__main">
                      <strong>{a.short_identity}</strong>
                      <span>
                        {a.tenant_name ? `${a.tenant_name} · ` : ''}
                        {a.attack_phase || a.cloud} · score {Number(a.score).toFixed(2)}
                      </span>
                    </span>
                    <ChevronRight size={14} aria-hidden />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="card dash-panel">
          <div className="dash-panel__head">
            <h3>Open cases</h3>
            <button type="button" className="link-button dash-panel__link" onClick={() => navigate('/cases')}>
              All cases
            </button>
          </div>
          {openCases.length === 0 ? (
            <div className="empty-state" style={{ padding: '1.5rem 0.5rem' }}>
              <p>No open cases. Escalate an alert from Triage to create one.</p>
            </div>
          ) : (
            <ul className="dash-list">
              {openCases.slice(0, 6).map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    className="dash-list__item"
                    onClick={() => navigate(`/cases?caseId=${c.id}`)}
                  >
                    <span className="dash-case-id">CASE-{String(c.id).padStart(4, '0')}</span>
                    <span className="dash-list__main">
                      <strong>{c.title}</strong>
                      <span>
                        {c.tenant_name ? `${c.tenant_name} · ` : ''}
                        {c.priority} · {c.status}
                      </span>
                    </span>
                    <ChevronRight size={14} aria-hidden />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <div className="dash-split">
        <section className="card dash-panel">
          <div className="dash-panel__head">
            <h3>
              <AlertTriangle size={16} style={{ marginRight: 6, verticalAlign: -2 }} />
              Detector disagreements
            </h3>
            <button type="button" className="link-button dash-panel__link" onClick={() => navigate('/analytics')}>
              Analytics
            </button>
          </div>
          {disagreements.length === 0 ? (
            <div className="empty-state" style={{ padding: '1.5rem 0.5rem' }}>
              <p>No stored quantum↔classical disagreements yet.</p>
            </div>
          ) : (
            <ul className="dash-list">
              {disagreements.slice(0, 5).map((row) => (
                <li key={row.id || row.alert_id}>
                  <button
                    type="button"
                    className="dash-list__item"
                    onClick={() => navigate(`/triage?alertId=${row.id || row.alert_id}`)}
                  >
                    <span className="dash-list__main">
                      <strong>{row.short_identity || row.identity || 'Alert'}</strong>
                      <span className="dash-list__clip">
                        {row.tenant_name ? `${row.tenant_name} · ` : ''}
                        {row.disagreement || 'Engines disagreed'}
                      </span>
                    </span>
                    <ChevronRight size={14} aria-hidden />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="card dash-panel">
          <div className="dash-panel__head">
            <h3>
              Risk trend
              <InfoBubble text="Live ensemble scores. Click a point with an alert to open Triage." />
            </h3>
            <button type="button" className="link-button dash-panel__link" onClick={() => navigate('/triage')}>
              Triage
            </button>
          </div>
          {state.history.length >= 2 ? (
            <div style={{ height: 220, width: '100%' }}>
              <ResponsiveContainer>
                <LineChart
                  data={state.history}
                  margin={{ top: 5, right: 12, bottom: 5, left: 0 }}
                  onClick={handleChartClick}
                  style={{ cursor: 'pointer' }}
                >
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border-color)" />
                  <XAxis dataKey="t" tick={{ fontSize: 11, fill: 'var(--text-secondary)' }} tickLine={false} axisLine={false} />
                  <YAxis domain={[0, 1]} tick={{ fontSize: 11, fill: 'var(--text-secondary)' }} tickLine={false} axisLine={false} width={28} />
                  <Tooltip
                    contentStyle={{ borderRadius: '6px', border: '1px solid var(--border-color)', background: 'var(--surface)' }}
                  />
                  <ReferenceLine y={state.threshold} stroke="var(--danger)" strokeDasharray="5 5" />
                  <Line type="monotone" dataKey="ensemble" stroke="var(--primary)" strokeWidth={2} dot={false} activeDot={{ r: 5 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="empty-state" style={{ height: 220 }}>
              <p>Start monitoring to populate the risk trend.</p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

export default Dashboard;

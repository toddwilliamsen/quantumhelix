import React from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import { useNavigate } from 'react-router-dom';
import InfoBubble from '../components/InfoBubble';

function Dashboard({ state }) {
  const navigate = useNavigate();
  const highestRisk = state.history.length > 0 
    ? Math.max(...state.history.map(h => h.ensemble)).toFixed(2)
    : "—";

  const handleChartClick = (data) => {
    if (data && data.activePayload && data.activePayload.length > 0) {
      const payload = data.activePayload[0].payload;
      if (payload.alert_id) {
        navigate(`/triage?alertId=${payload.alert_id}`);
      }
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Global Dashboard</h1>
        <p className="page-subtitle">Real-time overview of cloud security events and aggregate risk metrics.</p>
      </div>

      <div className="metrics-grid">
        <div className="metric-card">
          <div className="metric-label" style={{ display: 'flex', alignItems: 'center' }}>
            Events Watched <InfoBubble text="Total number of cloud security events analyzed since start." />
          </div>
          <div className="metric-value">{state.processed}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label" style={{ display: 'flex', alignItems: 'center' }}>
            Open Alerts <InfoBubble text="Number of alerts currently requiring analyst review." />
          </div>
          <div className="metric-value">{state.open_alerts}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label" style={{ display: 'flex', alignItems: 'center' }}>
            Highest Risk So Far <InfoBubble text="The highest ensemble anomaly score recorded in the current session." />
          </div>
          <div className="metric-value">{highestRisk}</div>
        </div>
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0, marginBottom: '0.5rem', display: 'flex', alignItems: 'center' }}>
          Live Risk Trend <InfoBubble text="Real-time chart of anomaly scores. Points above the threshold generate alerts." />
        </h3>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '1.5rem', fontSize: '0.875rem' }}>
          Each point is one cloud event. The red dashed line is your alert threshold. Click on any point that generated an alert to investigate.
        </p>
        
        {state.history.length >= 2 ? (
          <div style={{ height: 300, width: '100%' }}>
            <ResponsiveContainer>
              <LineChart 
                data={state.history} 
                margin={{ top: 5, right: 20, bottom: 5, left: 0 }}
                onClick={handleChartClick}
                style={{ cursor: 'pointer' }}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                <XAxis 
                  dataKey="t" 
                  tick={{ fontSize: 12, fill: '#64748b' }} 
                  tickLine={false} 
                  axisLine={false}
                />
                <YAxis 
                  domain={[0, 1]} 
                  tick={{ fontSize: 12, fill: '#64748b' }} 
                  tickLine={false} 
                  axisLine={false}
                />
                <Tooltip 
                  contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: 'var(--shadow-md)' }}
                  labelStyle={{ fontWeight: 'bold', color: '#0f172a' }}
                />
                <ReferenceLine y={state.threshold} stroke="#ef4444" strokeDasharray="5 5" />
                <Line 
                  type="monotone" 
                  dataKey="ensemble" 
                  stroke="#2563eb" 
                  strokeWidth={2} 
                  dot={false}
                  activeDot={{ r: 6, fill: '#2563eb', stroke: '#fff', strokeWidth: 2 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="empty-state" style={{ height: 300 }}>
            <p>Start watching to build the trend.</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default Dashboard;

import React, { useState, useEffect } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ScatterChart, Scatter, ZAxis } from 'recharts';
import toast from 'react-hot-toast';
import InfoBubble from '../components/InfoBubble';
import { apiFetch, getToken } from '../api';

function Analytics() {
  const [benchmark, setBenchmark] = useState(null);
  const [loading, setLoading] = useState(false);
  const [overview, setOverview] = useState(null);
  const [overviewError, setOverviewError] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    apiFetch('/api/analytics/overview', { signal: controller.signal })
      .then(setOverview)
      .catch((e) => {
        if (e.name !== 'AbortError') setOverviewError(e.message || 'Failed to load analytics');
      });
    return () => controller.abort();
  }, []);

  const runBenchmark = async () => {
    setLoading(true);
    try {
      const data = await apiFetch('/api/benchmark');
      setBenchmark(data);
    } catch (e) {
      console.error(e);
      toast.error('Failed to run benchmark');
    } finally {
      setLoading(false);
    }
  };

  const downloadReport = async () => {
    try {
      const token = getToken();
      const res = await fetch('/api/alerts/export', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!res.ok) throw new Error('Failed to download');
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'alerts_export.csv';
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (e) {
      console.error(e);
      toast.error('Failed to download report');
    }
  };

  const scatterData = overview?.feature_space || [];
  const normalData = scatterData.filter(d => d.type === 'normal');
  const anomalyData = scatterData.filter(d => d.type === 'anomaly');
  const latencyData = overview?.latency || [];
  const disagreements = overview?.disagreements || [];

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 className="page-title">Analytics & Models</h1>
          <p className="page-subtitle">Deep dive into the PCA feature space, quantum vs classical disagreements, and latency metrics.</p>
        </div>
        <div style={{ display: 'flex', gap: '1rem' }}>
          <button className="btn" onClick={downloadReport} style={{ background: 'var(--bg-primary)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}>
            Download Full Report (CSV)
          </button>
          <button className="btn btn-primary" onClick={runBenchmark} disabled={loading}>
            {loading ? 'Running...' : 'Run Offline Accuracy Check'}
          </button>
        </div>
      </div>

      {overviewError && (
        <p style={{ color: 'var(--danger)', marginBottom: '1rem' }}>{overviewError}</p>
      )}

      <div className="analytics-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
        <div className="card">
          <h3 style={{ marginTop: 0, display: 'flex', alignItems: 'center' }}>
            Feature Space Explorer (PCA 1 vs PCA 2) <InfoBubble text="Live 2D slice of the fitted classical PCA pipeline on a labeled synthetic corpus." />
          </h3>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '1rem' }}>
            Points from the fitted StandardScaler+PCA transform. Red = labeled attack corpus.
          </p>
          <div style={{ height: 300, width: '100%' }}>
            {!overview ? (
              <p style={{ color: 'var(--text-secondary)' }}>Loading feature space…</p>
            ) : scatterData.length === 0 ? (
              <p style={{ color: 'var(--text-secondary)' }}>Pipeline not ready yet — start the app detectors first.</p>
            ) : (
              <ResponsiveContainer>
                <ScatterChart margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis type="number" dataKey="x" name="PCA 1" />
                  <YAxis type="number" dataKey="y" name="PCA 2" />
                  <ZAxis type="number" dataKey="z" range={[60, 400]} />
                  <Tooltip cursor={{ strokeDasharray: '3 3' }} />
                  <Legend />
                  <Scatter name="Normal Telemetry" data={normalData} fill="#3b82f6" />
                  <Scatter name="Flagged events" data={anomalyData} fill="#ef4444" />
                </ScatterChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        <div className="card">
          <h3 style={{ marginTop: 0, display: 'flex', alignItems: 'center' }}>
            Simulation Latency Cost <InfoBubble text="Derived from recent HistoryEvent.latency_ms for your tenant (ensemble end-to-end), with approximate engine split." />
          </h3>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '1rem' }}>
            {overview?.latency_stats
              ? `n=${overview.latency_stats.samples}, mean=${overview.latency_stats.mean_ms}ms, p95=${overview.latency_stats.p95_ms}ms`
              : 'Waiting for streamed events…'}
          </p>
          <div style={{ height: 300, width: '100%' }}>
            <ResponsiveContainer>
              <BarChart data={latencyData} layout="vertical" margin={{ top: 20, right: 30, left: 40, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" dataKey="cost_ms" name="Latency (ms)" unit=" ms" />
                <YAxis type="category" dataKey="name" width={140} />
                <Tooltip cursor={{fill: 'transparent'}} />
                <Legend />
                <Bar dataKey="cost_ms" name="Inference Latency (ms)" fill="#8b5cf6" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: '2rem' }}>
        <h3 style={{ marginTop: 0, display: 'flex', alignItems: 'center' }}>
          Quantum vs Classical Disagreement View <InfoBubble text="Live alerts where detectors disagreed (stored disagreement text)." />
        </h3>
        <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '1rem' }}>
          Lifetime disagreement counter: {overview?.disagreement_count ?? '—'}
        </p>
        <div style={{ overflowX: 'auto' }}>
          <table className="alerts-table">
            <thead>
              <tr>
                <th>Event ID</th>
                <th>Identity</th>
                <th>Classical SVM</th>
                <th>Quantum Kernel</th>
                <th>Delta</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {disagreements.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ color: 'var(--text-secondary)', padding: '1rem' }}>
                    No disagreement alerts yet — run the stream to populate.
                  </td>
                </tr>
              ) : disagreements.map((row) => (
                <tr key={row.id}>
                  <td style={{ fontFamily: 'monospace', fontSize: '0.75rem' }}>{String(row.id).slice(0, 8)}…</td>
                  <td>{row.identity}</td>
                  <td>{Number(row.classical_svm).toFixed(2)}</td>
                  <td>{Number(row.quantum_kernel).toFixed(2)}</td>
                  <td>{row.delta}</td>
                  <td>{row.status} / {row.severity}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {loading ? (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Offline Benchmark Metrics</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <div style={{ height: '2rem', background: 'var(--bg-primary)', borderRadius: '4px', animation: 'pulse 1.5s infinite' }} />
            <div style={{ height: '2rem', background: 'var(--bg-primary)', borderRadius: '4px', animation: 'pulse 1.5s infinite' }} />
            <style>{`@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .5; } }`}</style>
          </div>
        </div>
      ) : !benchmark ? null : (
        <div className="card">
          <h3 style={{ marginTop: 0, display: 'flex', alignItems: 'center' }}>
            Offline Benchmark Metrics <InfoBubble text="Evaluation metrics from the latest offline benchmark suite." />
          </h3>
          <div style={{ overflowX: 'auto' }}>
            <table>
              <thead>
                <tr>
                  <th>Detector</th>
                  <th>Detect Rate</th>
                  <th>False Alarms</th>
                  <th>Subtle Attacks</th>
                  <th>Loud Attacks</th>
                  <th>AUC</th>
                  <th>Fit (s)</th>
                  <th>ms/event</th>
                </tr>
              </thead>
              <tbody>
                {benchmark.map((row, i) => (
                  <tr key={i}>
                    <td style={{ fontWeight: 600 }}>{row.name}</td>
                    <td>{(row.detection_rate * 100).toFixed(1)}%</td>
                    <td>{(row.false_positive_rate * 100).toFixed(1)}%</td>
                    <td>{(row.subtle_apt_recall * 100).toFixed(1)}%</td>
                    <td>{(row.loud_attack_recall * 100).toFixed(1)}%</td>
                    <td>{row.roc_auc.toFixed(3)}</td>
                    <td>{row.fit_seconds.toFixed(3)}</td>
                    <td>{row.mean_score_ms.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

export default Analytics;

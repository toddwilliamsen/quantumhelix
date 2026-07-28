import React, { useState, useEffect } from 'react';
import { Sliders, Cpu, Activity, Save } from 'lucide-react';
import { toast } from 'react-hot-toast';
import { apiFetch } from '../api';

function Playground({ token }) {
  const readOnly = localStorage.getItem('quantum_role') === 'READ_ONLY';
  const [config, setConfig] = useState({
    pca_dimensions: 4,
    kernel_type: 'simulator',
    ensemble_weights: {
      classical: 55,
      quantum: 45
    },
    latency_profile: 'balanced'
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      try {
        const data = await apiFetch('/api/playground/config', { token, signal: controller.signal });
        const classical = data.ensemble_weights?.classical ?? 0.55;
        const quantum = data.ensemble_weights?.quantum ?? 0.45;
        setConfig({
          pca_dimensions: data.pca_dimensions ?? 4,
          kernel_type: data.kernel_type ?? 'simulator',
          ensemble_weights: {
            classical: classical <= 1 ? Math.round(classical * 100) : Math.round(classical),
            quantum: quantum <= 1 ? Math.round(quantum * 100) : Math.round(quantum),
          },
          latency_profile: data.latency_profile ?? 'balanced',
        });
      } catch (e) {
        if (e.name !== 'AbortError') console.error(e);
      } finally {
        setLoading(false);
      }
    })();
    return () => controller.abort();
  }, [token]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = {
        ...config,
        ensemble_weights: {
          classical: config.ensemble_weights.classical / 100,
          quantum: config.ensemble_weights.quantum / 100,
        },
      };
      await apiFetch('/api/playground/config', {
        method: 'POST',
        token,
        json: payload,
      });
      toast.success('Model settings updated');
    } catch (e) {
      toast.error(e.message || "Failed to update configuration.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div><p style={{ color: 'var(--text-secondary)' }}>Loading model settings…</p></div>;
  }

  return (
    <div>
      <header className="page-header">
        <h1 className="page-title">Model controls</h1>
        <p className="page-subtitle">Adjust live scoring weights and simulation cadence.</p>
      </header>

      <div className="model-settings-grid">
        
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem', color: 'var(--text-secondary)' }}>
            <Activity size={18} />
            <h2>Feature pipeline</h2>
          </div>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>
            The normalized event vector is scaled and reduced before model inference.
          </p>
          
          <div style={{ marginBottom: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
              <label style={{ fontWeight: 600 }} htmlFor="pca-dims">PCA dimensions</label>
              <span className="status-pill">4 · fixed</span>
            </div>
            <input 
              id="pca-dims"
              type="range" 
              min="4" max="4" step="1"
              value={4}
              disabled
              aria-valuetext="4 (locked to quantum AngleEmbedding width)"
              style={{ width: '100%', opacity: 0.5 }}
            />
            <small style={{ color: 'var(--text-secondary)', display: 'block', marginTop: '0.5rem' }}>
              Fixed to the four-qubit AngleEmbedding width. A width change requires model retraining.
            </small>
          </div>

          <div style={{ marginTop: '1.5rem' }}>
            <label className="control-label" style={{ display: 'block', marginBottom: '0.5rem' }} htmlFor="latency">Simulation cadence</label>
            <select
              id="latency"
              className="form-control"
              value={config.latency_profile}
              disabled={readOnly}
              onChange={(e) => setConfig({ ...config, latency_profile: e.target.value })}
            >
              <option value="fast">Fast · 0.25 seconds</option>
              <option value="balanced">Balanced · 0.65 seconds</option>
              <option value="thorough">Reduced load · 1.2 seconds</option>
            </select>
          </div>
        </div>

        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem', color: 'var(--text-secondary)' }}>
            <Cpu size={18} />
            <h2>Kernel runtime</h2>
          </div>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>
            Runtime used by the quantum-kernel model in this deployment.
          </p>
          
          <div style={{ padding: '14px', border: '1px solid var(--border-color)', borderRadius: '6px', background: 'var(--surface-subtle)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'center' }}>
              <div>
                <strong>Local statevector simulator</strong>
                <div style={{ marginTop: 3, color: 'var(--text-secondary)', fontSize: '0.82rem' }}>
                  PennyLane default.qubit · four wires
                </div>
              </div>
              <span className="status-pill is-success">Active</span>
            </div>
          </div>
        </div>

        <div className="card" style={{ gridColumn: '1 / -1' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem', color: 'var(--text-secondary)' }}>
            <Sliders size={18} />
            <h2>Ensemble weighting</h2>
          </div>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>
            Set the contribution of the classical baseline and quantum kernel to the final risk score.
          </p>
          
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <span style={{ minWidth: '110px', fontWeight: 600, color: 'var(--primary)' }}>Classical · {config.ensemble_weights.classical}%</span>
            <input 
              type="range" 
              min="0" max="100" step="5" 
              value={config.ensemble_weights.classical}
              aria-label="Classical ensemble weight"
              disabled={readOnly}
              onChange={(e) => {
                const val = parseInt(e.target.value);
                setConfig({
                  ...config, 
                  ensemble_weights: { classical: val, quantum: 100 - val }
                });
              }}
              style={{ flex: 1 }}
            />
            <span style={{ minWidth: '110px', fontWeight: 600, textAlign: 'right', color: 'var(--text-primary)' }}>Quantum · {config.ensemble_weights.quantum}%</span>
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        {readOnly ? (
          <span style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>Read-only access</span>
        ) : (
        <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
          <Save size={16} /> {saving ? 'Saving…' : 'Save changes'}
        </button>
        )}
      </div>
    </div>
  );
}

export default Playground;

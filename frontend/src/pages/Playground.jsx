import React, { useState } from 'react';
import { Sliders, Cpu, Activity, Save } from 'lucide-react';
import { toast } from 'react-hot-toast';

function Playground({ token }) {
  const [config, setConfig] = useState({
    pca_dimensions: 4,
    kernel_type: 'simulator',
    ensemble_weights: {
      classical: 55,
      quantum: 45
    },
    latency_profile: 'balanced'
  });

  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch('/api/playground/config', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(config)
      });
      if (res.ok) {
        toast.success("Ensemble configuration updated (Simulated)", { icon: '⚙️' });
      } else {
        toast.error("Failed to update configuration.");
      }
    } catch (e) {
      toast.error("Error communicating with backend.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="dashboard">
      <header className="header">
        <h1>Model Playground</h1>
        <p>Experiment with the hybrid ensemble architecture and tune the threat models in real-time.</p>
      </header>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem', marginTop: '2rem' }}>
        
        {/* Classical Settings */}
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem', color: 'var(--text-secondary)' }}>
            <Activity size={18} />
            <h2>Classical Dimensionality Reduction</h2>
          </div>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>
            Adjust the number of Principal Components extracted from the normalized Common Information Model before passing to the quantum layer.
          </p>
          
          <div style={{ marginBottom: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
              <label style={{ fontWeight: '500' }}>PCA Dimensions (Qubit Width)</label>
              <span>{config.pca_dimensions} Components</span>
            </div>
            <input 
              type="range" 
              min="2" max="8" step="1" 
              value={config.pca_dimensions}
              onChange={(e) => setConfig({...config, pca_dimensions: parseInt(e.target.value)})}
              style={{ width: '100%' }}
            />
            <small style={{ color: 'var(--text-secondary)', display: 'block', marginTop: '0.5rem' }}>
              Note: Higher dimensions require exponentially more qubits for AngleEmbedding.
            </small>
          </div>
        </div>

        {/* Quantum Settings */}
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem', color: 'var(--text-secondary)' }}>
            <Cpu size={18} />
            <h2>Quantum Hardware Configuration</h2>
          </div>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>
            Select the execution backend for the PennyLane QSVM.
          </p>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <input 
                type="radio" 
                name="kernel" 
                value="simulator" 
                checked={config.kernel_type === 'simulator'} 
                onChange={(e) => setConfig({...config, kernel_type: e.target.value})}
              />
              <span><strong>Statevector Simulator</strong> (Lightning.qubit, fast classical simulation)</span>
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <input 
                type="radio" 
                name="kernel" 
                value="ibm_quantum" 
                checked={config.kernel_type === 'ibm_quantum'} 
                onChange={(e) => setConfig({...config, kernel_type: e.target.value})}
              />
              <span><strong>IBM Quantum</strong> (Simulated hardware shot execution)</span>
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', opacity: 0.5 }}>
              <input type="radio" disabled />
              <span><strong>IonQ Aria</strong> (Offline/Unavailable)</span>
            </label>
          </div>
        </div>

        {/* Ensemble Weighting */}
        <div className="card" style={{ gridColumn: '1 / -1' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem', color: 'var(--text-secondary)' }}>
            <Sliders size={18} />
            <h2>Hybrid Ensemble Weighting</h2>
          </div>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>
            Adjust the confidence weight distributed between the Classical Baseline (Isolation Forest + SVM) and the Quantum Kernel.
          </p>
          
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <span style={{ minWidth: '100px', fontWeight: '500', color: '#3b82f6' }}>Classical ({config.ensemble_weights.classical}%)</span>
            <input 
              type="range" 
              min="0" max="100" step="5" 
              value={config.ensemble_weights.classical}
              onChange={(e) => {
                const val = parseInt(e.target.value);
                setConfig({
                  ...config, 
                  ensemble_weights: { classical: val, quantum: 100 - val }
                });
              }}
              style={{ flex: 1 }}
            />
            <span style={{ minWidth: '100px', fontWeight: '500', textAlign: 'right', color: '#8b5cf6' }}>Quantum ({config.ensemble_weights.quantum}%)</span>
          </div>
        </div>
      </div>

      <div style={{ marginTop: '2rem', display: 'flex', justifyContent: 'flex-end' }}>
        <button className="btn btn-primary" onClick={handleSave} disabled={saving} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Save size={18} /> {saving ? "Applying..." : "Apply Configuration"}
        </button>
      </div>

      <div className="card" style={{ marginTop: '2rem', background: 'var(--bg-card)', border: '1px solid #10b981', color: '#10b981' }}>
        <h3 style={{ marginBottom: '0.5rem', color: '#10b981' }}>Future Quantum Hardware Readiness</h3>
        <p style={{ fontSize: '0.9rem', lineHeight: '1.5' }}>
          If run on a real Quantum Processing Unit (QPU) rather than a statevector simulator, this kernel architecture would scale differently.
          The classical complexity of computing kernel entries grows exponentially with feature dimension, whereas a QPU can evaluate the inner product directly via a SWAP test or inversion circuit in O(1) circuit depth, offering a theoretical exponential speedup for high-dimensional threat spaces.
        </p>
      </div>
    </div>
  );
}

export default Playground;

import React from 'react';
import InfoBubble from './InfoBubble';

const SEV_COLOR = {
  critical: 'var(--danger)',
  high: 'var(--danger)',
  elevated: 'var(--warning)',
  normal: 'var(--text-tertiary)',
};

function SignalBar({ signal }) {
  const pct = Math.min(100, Math.max(8, Math.log10(Math.max(signal.ratio, 1) + 1) * 55));
  return (
    <div className="explain-signal">
      <div className="explain-signal__head">
        <span>{signal.label}</span>
        <span className="explain-signal__value">
          {signal.value}{signal.unit ? ` ${signal.unit}` : ''}
          <span className="explain-signal__baseline"> / baseline {signal.baseline}</span>
        </span>
      </div>
      <div className="explain-signal__track">
        <div
          className="explain-signal__fill"
          style={{ width: `${pct}%`, background: SEV_COLOR[signal.severity] || 'var(--primary)' }}
        />
      </div>
      <p className="explain-signal__why">{signal.why}</p>
    </div>
  );
}

/**
 * Structured intrusion explanation panel shared by Triage + EventDrillDown.
 */
export default function IntrusionExplanation({ alert }) {
  const contrib = (alert && typeof alert.feature_contributions === 'object' && alert.feature_contributions)
    ? alert.feature_contributions
    : null;
  const signals = Array.isArray(contrib?.signals) ? contrib.signals : [];
  const techniques = Array.isArray(contrib?.techniques) ? contrib.techniques : [];
  const disagreement = contrib?.engines?.disagreement || null;
  const hypothesis = contrib?.hypothesis;

  return (
    <div className="explain-panel">
      <h4 className="explain-panel__title">
        Intrusion explanation
        <InfoBubble text="Structured hypotheses from CIM signals and hybrid ensemble scores. Technique IDs are analyst orientation aids, not certified ATT&CK matches." />
      </h4>

      {(hypothesis || alert?.attack_phase) && (
        <div className="explain-hypothesis">
          <span className="explain-phase">{alert?.attack_phase || contrib?.attack_phase}</span>
          <span>{hypothesis || `Phase hypothesis: ${alert?.attack_phase}`}</span>
        </div>
      )}

      <p className="explain-narrative">{alert?.plain_english}</p>

      {techniques.length > 0 && (
        <div className="explain-techniques">
          <div className="explain-section-label">Technique hypotheses</div>
          <ul>
            {techniques.map((t) => (
              <li key={`${t.id}-${t.name}`}>
                <code>{t.id}</code>
                <strong>{t.name}</strong>
                <span className={`explain-conf is-${t.confidence || 'low'}`}>{t.confidence}</span>
                <span className="explain-evidence">{t.evidence}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {signals.length > 0 && (
        <div className="explain-signals">
          <div className="explain-section-label">Driving signals vs baseline</div>
          {signals.map((s) => <SignalBar key={s.name} signal={s} />)}
        </div>
      )}

      {disagreement && (
        <div className="notice-warning explain-disagreement">
          <strong>Detector disagreement</strong>
          <p>{disagreement.interpretation || disagreement.summary}</p>
          <div className="explain-engine-row">
            <span>Q {Number(disagreement.quantum_kernel).toFixed(2)}</span>
            <span>SVM {Number(disagreement.classical_svm).toFixed(2)}</span>
            <span>IF {Number(disagreement.isolation_forest).toFixed(2)}</span>
            <span>Δ {Number(disagreement.delta).toFixed(2)}</span>
          </div>
        </div>
      )}

      {!contrib?.version && (
        <p className="explain-legacy">
          Open “Generate explanation” for a rebuilt brief on older alerts that predate structured contributions.
        </p>
      )}
    </div>
  );
}

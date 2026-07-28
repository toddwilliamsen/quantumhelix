import React from 'react';
import { Activity, Cloud, Clock } from 'lucide-react';

const ThreatGraph = ({ phases, identities, selectedIdentityId, setSelectedIdentityId, getSeverityColor }) => {
  return (
    <div style={{ flex: 1, display: 'flex', gap: '1rem', overflowX: 'auto', padding: '0 1.5rem 1.5rem 1.5rem' }}>
      {phases.map((phase, idx) => (
        <div key={phase} style={{ flex: 1, minWidth: '260px', background: 'var(--bg-secondary)', borderRadius: '8px', padding: '1rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <h3 style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em', display: 'flex', alignItems: 'center', gap: '0.5rem', margin: 0 }}>
            <span style={{ background: 'var(--bg-primary)', width: '20px', height: '20px', display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: '50%', fontSize: '0.7rem' }}>{idx + 1}</span> 
            {phase}
          </h3>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', flex: 1 }}>
            {identities.filter(idObj => {
              const knownPhaseIndexes = Array.from(idObj.phases)
                .map(p => phases.indexOf(p))
                .filter(index => index >= 0);
              const highestPhaseIdx = knownPhaseIndexes.length > 0 ? Math.max(...knownPhaseIndexes) : 0;
              return phases.indexOf(phase) === highestPhaseIdx;
            }).map(idObj => {
              const color = getSeverityColor(idObj.maxScore);
              const isSelected = selectedIdentityId === idObj.identity;
              
              return (
                <button
                  type="button"
                  key={idObj.identity}
                  className="threat-card"
                  aria-pressed={isSelected}
                  onClick={() => setSelectedIdentityId(idObj.identity)}
                  style={{
                    background: 'var(--bg-primary)',
                    border: `1px solid ${isSelected ? color : 'var(--border-color)'}`,
                    borderRadius: '8px',
                    padding: '1rem',
                    boxShadow: isSelected ? `0 0 0 1px ${color}` : '0 1px 3px rgba(0,0,0,0.1)',
                    cursor: 'pointer',
                    transition: 'transform 0.1s ease, box-shadow 0.1s ease',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '0.75rem',
                    color: 'var(--text-primary)',
                    font: 'inherit',
                    textAlign: 'left'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', overflow: 'hidden' }}>
                      <Activity size={16} color={color} />
                      <span style={{ fontWeight: 600, fontSize: '0.9rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={idObj.identity}>
                        {idObj.short_identity}
                      </span>
                    </div>
                  </div>
                  
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                      <Cloud size={12} /> {idObj.cloud}
                    </span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                      <Clock size={12} /> {new Date(idObj.latestTimestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <div style={{ flex: 1, height: '6px', background: 'var(--bg-secondary)', borderRadius: '3px', overflow: 'hidden' }}>
                      <div style={{ width: `${Math.min(idObj.maxScore * 100, 100)}%`, height: '100%', background: color }} />
                    </div>
                    <span style={{ fontSize: '0.75rem', fontWeight: 600, color: color }}>
                      {idObj.maxScore.toFixed(3)}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
};

export default ThreatGraph;

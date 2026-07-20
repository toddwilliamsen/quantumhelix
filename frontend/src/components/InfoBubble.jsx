import React, { useState } from 'react';
import { Info } from 'lucide-react';

function InfoBubble({ text }) {
  const [show, setShow] = useState(false);

  return (
    <div 
      className="tooltip-container"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
      style={{ display: 'inline-flex', alignItems: 'center', marginLeft: '0.5rem', position: 'relative', cursor: 'help' }}
    >
      <Info size={16} color="var(--text-secondary)" />
      {show && (
        <div 
          className="tooltip-text"
          style={{
            position: 'absolute',
            bottom: '125%',
            left: '50%',
            transform: 'translateX(-50%)',
            backgroundColor: 'var(--text-primary)',
            color: '#fff',
            padding: '0.5rem 0.75rem',
            borderRadius: '6px',
            fontSize: '0.75rem',
            fontWeight: 400,
            whiteSpace: 'nowrap',
            zIndex: 50,
            pointerEvents: 'none',
            boxShadow: 'var(--shadow-md)'
          }}
        >
          {text}
          <div style={{
            position: 'absolute',
            top: '100%',
            left: '50%',
            marginLeft: '-5px',
            borderWidth: '5px',
            borderStyle: 'solid',
            borderColor: 'var(--text-primary) transparent transparent transparent'
          }}></div>
        </div>
      )}
    </div>
  );
}

export default InfoBubble;

import React, { useState } from 'react';
import { Info } from 'lucide-react';

function InfoBubble({ text }) {
  const [show, setShow] = useState(false);

  return (
    <span
      className="tooltip-container"
    >
      <button
        type="button"
        className="tooltip-trigger"
        aria-label={text}
        aria-expanded={show}
        onMouseEnter={() => setShow(true)}
        onMouseLeave={() => setShow(false)}
        onFocus={() => setShow(true)}
        onBlur={() => setShow(false)}
        onClick={() => setShow(value => !value)}
      >
        <Info size={14} />
      </button>
      {show && (
        <span
          className="tooltip-text"
          role="tooltip"
        >
          {text}
        </span>
      )}
    </span>
  );
}

export default InfoBubble;

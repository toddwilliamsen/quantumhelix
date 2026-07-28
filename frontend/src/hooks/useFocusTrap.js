import { useEffect, useRef } from 'react';

/**
 * Trap focus inside a modal dialog and restore focus on unmount.
 * @param {boolean} active
 */
export function useFocusTrap(active = true) {
  const containerRef = useRef(null);
  const previousFocus = useRef(null);

  useEffect(() => {
    if (!active) return undefined;
    previousFocus.current = document.activeElement;
    const node = containerRef.current;
    if (!node) return undefined;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const focusableSelector =
      'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

    const focusFirst = () => {
      const list = node.querySelectorAll(focusableSelector);
      if (list.length) list[0].focus();
      else node.focus();
    };
    // Defer so dialog content is mounted
    const t = setTimeout(focusFirst, 0);

    const onKeyDown = (e) => {
      if (e.key !== 'Tab') return;
      const list = Array.from(node.querySelectorAll(focusableSelector)).filter(
        (el) => el.offsetParent !== null || el === document.activeElement
      );
      if (!list.length) {
        e.preventDefault();
        return;
      }
      const first = list[0];
      const last = list[list.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };

    node.addEventListener('keydown', onKeyDown);
    return () => {
      clearTimeout(t);
      node.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = previousOverflow;
      if (previousFocus.current && previousFocus.current.focus) {
        previousFocus.current.focus();
      }
    };
  }, [active]);

  return containerRef;
}

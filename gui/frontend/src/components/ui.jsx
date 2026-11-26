/**
 * Small shared UI pieces used by several screens.
 */
import { useEffect, useRef } from 'react';

/** Accessible in-app dialog (replaces window.confirm). */
export function Modal({ title, children, actions, onClose }) {
  const ref = useRef(null);

  useEffect(() => {
    const prev = document.activeElement;
    ref.current?.querySelector('button')?.focus();
    function onKey(e) { if (e.key === 'Escape') onClose?.(); }
    window.addEventListener('keydown', onKey);
    return () => { window.removeEventListener('keydown', onKey); prev?.focus?.(); };
  }, [onClose]);

  return (
    <div className="modal-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) onClose?.(); }}>
      <div ref={ref} className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <h2 id="modal-title" style={{ fontSize: 17, fontWeight: 700, color: '#fff', marginBottom: 10 }}>{title}</h2>
        <div className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>{children}</div>
        <div className="flex flex-wrap justify-end gap-2 mt-6">{actions}</div>
      </div>
    </div>
  );
}

/** One number + label tile. */
export function Stat({ value, label, color }) {
  return (
    <div className="stat">
      <span className="stat-value" style={{ color: color || '#fff' }}>{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  );
}

/** Screen header used by Settings / Run / Done. */
export function ScreenHeader({ title, subtitle, children, accent }) {
  return (
    <>
      <div className="accent-bar" style={accent ? { background: `linear-gradient(90deg, transparent 0%, ${accent} 50%, transparent 100%)` } : undefined} />
      <header className="screen-header">
        <div className="accent-stripe" style={accent ? { background: accent, boxShadow: 'none' } : undefined} />
        <div className="flex-1 min-w-0">
          <h1 style={{ fontSize: 20, fontWeight: 700, color: '#fff', letterSpacing: '-0.4px' }}>{title}</h1>
          {subtitle && <div className="text-xs mt-0.5 truncate" style={{ color: 'var(--text-secondary)' }}>{subtitle}</div>}
        </div>
        {children}
      </header>
    </>
  );
}

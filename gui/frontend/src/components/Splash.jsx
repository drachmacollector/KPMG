/**
 * Splash.jsx
 *
 * Welcome / launch screen — the first thing the user sees.
 *
 * Layout (centred card on a deep gradient background):
 *   ┌──────────────────────────────┐
 *   │  [icon / monogram]           │
 *   │  MahaBOCW Verification Tool  │
 *   │  (tagline, 2 lines)          │
 *   │  [v 1.0.0 pill]              │
 *   │  ─────────────────────────   │
 *   │  [ Launch Application → ]    │
 *   └──────────────────────────────┘
 *
 * Animations:
 *   • Card fades in from opacity 0 on mount (CSS animation).
 *   • Launch button has a persistent pulsing glow (CSS keyframes).
 */

export default function Splash({ onLaunch }) {
  return (
    <div
      className="flex items-center justify-center h-full w-full"
    >
      {/* Card — fades in on mount */}
      <div
        className="card flex flex-col items-center text-center px-14 py-14 w-[500px]"
        style={{
          animation: 'fadeIn 0.8s cubic-bezier(0.16,1,0.3,1) both, float 6s ease-in-out infinite',
        }}
      >
        {/* App icon / logo */}
        <div className="flex items-center justify-center mb-6 rounded-2xl overflow-hidden" style={{ width: 100, height: 100, background: 'var(--accent-subtle)', border: '1px solid var(--border-accent)' }}>
          <img src="./logo.png" alt="MAHABOCW Logo" className="w-full h-full object-contain" />
        </div>

        {/* Title */}
        <h1
          className="font-extrabold tracking-tight mb-4"
          style={{
            fontSize: 28,
            color: '#fff',
            letterSpacing: '-0.5px',
            lineHeight: 1.2,
          }}
        >
          MahaBOCW<br />Verification Tool
        </h1>

        {/* Tagline */}
        <p
          className="text-sm leading-relaxed mb-5"
          style={{ color: 'var(--text-secondary)', maxWidth: 340 }}
        >
          Automated OCR &amp; web-based college verification pipeline.<br />
          Processes beneficiary records against the MahaDBT portal in bulk.
        </p>

        {/* Version pill */}
        <span
          className="pill mb-10"
          style={{
            color: 'var(--text-accent)',
            background: 'var(--accent-subtle)',
            border: '1px solid var(--border-accent)',
          }}
        >
          v 1.0.0
        </span>

        {/* Divider */}
        <div
          className="w-full mb-10"
          style={{ height: 1, background: 'var(--border)' }}
        />

        {/* Launch button */}
        <button
          id="btn-launch"
          className="btn-primary w-full text-base font-bold py-3"
          style={{ height: 52, fontSize: 15, borderRadius: 12 }}
          onClick={onLaunch}
        >
          Launch Application &nbsp;→
        </button>

        {/* Footer note */}
        <p className="mt-4 text-xs" style={{ color: 'var(--text-muted)' }}>
          Maharashtra BOCW · Beneficiary Verification
        </p>
      </div>
    </div>
  );
}

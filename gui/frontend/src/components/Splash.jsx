/**
 * Splash.jsx — welcome screen.
 */
import { ArrowRight } from 'lucide-react';

/* global __APP_VERSION__ */
const VERSION = typeof __APP_VERSION__ !== 'undefined' ? __APP_VERSION__ : 'dev';

export default function Splash({ onLaunch }) {
  return (
    <div className="flex items-center justify-center h-full w-full">
      <div
        className="card flex flex-col items-center text-center px-14 py-14 w-[500px]"
        style={{ animation: 'fadeIn 0.8s cubic-bezier(0.16,1,0.3,1) both' }}
      >
        <div className="flex items-center justify-center mb-6 rounded-2xl overflow-hidden"
             style={{ width: 100, height: 100, background: 'var(--accent-subtle)', border: '1px solid var(--border-accent)' }}>
          <img src="./logo.png" alt="" className="w-full h-full object-contain" />
        </div>

        <h1 className="font-extrabold tracking-tight mb-4" style={{ fontSize: 28, color: '#fff', letterSpacing: '-0.5px', lineHeight: 1.35 }}>
          MahaBOCW<br />Verification Tool
        </h1>

        <p className="text-sm leading-relaxed mb-5" style={{ color: 'var(--text-secondary)', maxWidth: 360 }}>
          Reads claim documents, finds each student's college, checks it online,
          and writes the corrected names and addresses back to your Excel sheet.
        </p>

        <span className="pill mb-10" style={{ color: 'var(--text-accent)', background: 'var(--accent-subtle)', border: '1px solid var(--border-accent)' }}>
          v{VERSION}
        </span>

        <div className="w-full mb-10" style={{ height: 1, background: 'var(--border)' }} />

        <button id="btn-launch" className="btn-primary w-full gap-2" style={{ height: 52, fontSize: 15, borderRadius: 12 }} onClick={onLaunch} autoFocus>
          Get started <ArrowRight size={18} aria-hidden />
        </button>

        <p className="mt-4 text-xs" style={{ color: 'var(--text-muted)' }}>
          Maharashtra BOCW · Beneficiary Verification
        </p>
      </div>
    </div>
  );
}

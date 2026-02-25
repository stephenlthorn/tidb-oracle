'use client';

import Link from 'next/link';
import Image from 'next/image';
import { usePathname } from 'next/navigation';
import { useState } from 'react';

const PERSONAS = [
  { href: '/rep',       label: 'Sales Rep',     icon: '◎' },
  { href: '/se',        label: 'Sales Engineer', icon: '⬡' },
  { href: '/marketing', label: 'Marketing',      icon: '◈' },
  { href: '/admin',     label: 'Admin',          icon: '⊞' },
];

const UTILITY = [
  { href: '/settings', label: 'Settings', icon: '⚙' },
];

export default function Sidebar({ email }) {
  const pathname = usePathname();
  const [loggingOut, setLoggingOut] = useState(false);

  const handleLogout = async () => {
    setLoggingOut(true);
    await fetch('/api/auth/logout', { method: 'POST' });
    window.location.href = '/login';
  };

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <Image alt="TiDB" src="/tidb-logo.png" width={22} height={22} />
        <div>
          <div className="sidebar-brand-name">TiDB Oracle</div>
          <div className="sidebar-brand-sub">GTM Copilot</div>
        </div>
      </div>

      <nav className="sidebar-nav">
        <div className="sidebar-section-label">Persona</div>
        {PERSONAS.map(({ href, label, icon }) => (
          <Link
            key={href}
            href={href}
            className={`nav-link${pathname.startsWith(href) ? ' active' : ''}`}
          >
            <span className="nav-link-icon">{icon}</span>
            {label}
          </Link>
        ))}

        <div className="sidebar-section-label" style={{ marginTop: '0.5rem' }}>Account</div>
        {UTILITY.map(({ href, label, icon }) => (
          <Link
            key={href}
            href={href}
            className={`nav-link${pathname.startsWith(href) ? ' active' : ''}`}
          >
            <span className="nav-link-icon">{icon}</span>
            {label}
          </Link>
        ))}
      </nav>

      <div className="sidebar-footer">
        <div className="user-row">
          <div className="user-dot" />
          <div className="user-email">{email}</div>
        </div>
        <button
          className="nav-link btn-ghost"
          onClick={handleLogout}
          disabled={loggingOut}
          style={{ width: '100%' }}
        >
          <span className="nav-link-icon">→</span>
          {loggingOut ? 'Signing out...' : 'Sign out'}
        </button>
      </div>
    </aside>
  );
}

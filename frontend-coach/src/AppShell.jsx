import React, { useState, useEffect, useRef } from 'react'

const T = {
  sidebar: '#123D2F',
  lime:    '#CBEA58',
  muted:   'rgba(255,255,255,0.45)',
  mutedLo: 'rgba(255,255,255,0.18)',
  primary: '#17231D',
  border:  '#DCE4DE',
  muted2:  '#65716B',
}

const W = 240
const R = 80

const NAV = [
  { key: 'dashboard', label: 'Dashboard', icon: '⊞' },
  { key: 'roster',    label: 'Roster',    icon: '◉',  requiresTeam: true },
  { key: 'reports',   label: 'Reports',   icon: '▤' },
]

function initials(name) {
  if (!name) return 'C'
  return name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
}

function navHandler(key, callbacks) {
  if (key === 'dashboard') return callbacks.onDashboard
  if (key === 'roster')    return callbacks.onRoster
  if (key === 'reports')   return callbacks.onReports
  return null
}

// ── Settings Modal ────────────────────────────────────────────────────────────

function usePref(key, defaultVal) {
  const [val, setVal] = useState(() => {
    try { const s = localStorage.getItem(key); return s !== null ? JSON.parse(s) : defaultVal }
    catch { return defaultVal }
  })
  function set(v) { setVal(v); try { localStorage.setItem(key, JSON.stringify(v)) } catch {} }
  return [val, set]
}

function Toggle({ checked, onChange, label, description }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16 }}>
      <div>
        <div style={{ fontSize: 14, fontWeight: 600, color: T.primary }}>{label}</div>
        {description && <div style={{ fontSize: 12, color: T.muted2, marginTop: 2 }}>{description}</div>}
      </div>
      <button
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        style={{
          width: 44, height: 24, borderRadius: 12, flexShrink: 0, cursor: 'pointer',
          background: checked ? '#CBEA58' : '#DCE4DE', border: 'none',
          position: 'relative', transition: 'background .2s',
        }}
      >
        <span style={{
          position: 'absolute', top: 3, left: checked ? 23 : 3,
          width: 18, height: 18, borderRadius: '50%', background: '#fff',
          boxShadow: '0 1px 3px rgba(0,0,0,.2)',
          transition: 'left .2s',
        }} />
      </button>
    </div>
  )
}

function SettingsModal({ coachName, onClose, onLogout }) {
  const [weeklyDigest,    setWeeklyDigest]    = usePref('coach_weekly_digest',    true)
  const [showAnalytics,   setShowAnalytics]   = usePref('coach_show_analytics',   true)
  const [compactCards,    setCompactCards]    = usePref('coach_compact_cards',    false)
  const panelRef = useRef(null)

  useEffect(() => {
    const onKey = e => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    panelRef.current?.focus()
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const section = (title) => (
    <div style={{ fontSize: 11, fontWeight: 700, color: T.muted2, textTransform: 'uppercase',
                  letterSpacing: '.07em', marginBottom: 12, marginTop: 20 }}>
      {title}
    </div>
  )

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,.55)',
        zIndex: 500, display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 16,
      }}
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        onClick={e => e.stopPropagation()}
        style={{
          background: '#fff', borderRadius: 20, width: '100%', maxWidth: 460,
          maxHeight: '90vh', overflowY: 'auto',
          boxShadow: '0 20px 60px rgba(0,0,0,.25)',
          outline: 'none',
        }}
      >
        {/* Header */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '20px 24px 16px',
          borderBottom: `1px solid ${T.border}`,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 20 }}>⚙</span>
            <span style={{ fontSize: 18, fontWeight: 700, color: T.primary }}>Settings</span>
          </div>
          <button onClick={onClose} aria-label="Close settings" style={{
            background: 'none', border: 'none', cursor: 'pointer',
            fontSize: 20, color: T.muted2, lineHeight: 1, padding: 4,
          }}>✕</button>
        </div>

        <div style={{ padding: '4px 24px 24px' }}>

          {/* Profile */}
          {section('Profile')}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 14,
            padding: '14px 16px', background: '#EAF2EC',
            borderRadius: 12, border: `1px solid ${T.border}`,
          }}>
            <div style={{
              width: 48, height: 48, borderRadius: '50%',
              background: '#BFD9C6', display: 'flex', alignItems: 'center',
              justifyContent: 'center', fontSize: 18, fontWeight: 700, color: '#1E5A45',
            }}>
              {initials(coachName)}
            </div>
            <div>
              <div style={{ fontWeight: 700, fontSize: 15, color: T.primary }}>{coachName || 'Coach'}</div>
              <div style={{ fontSize: 13, color: T.muted2, marginTop: 2 }}>Head Coach</div>
            </div>
          </div>

          {/* Preferences */}
          {section('Preferences')}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <Toggle
              checked={weeklyDigest}
              onChange={setWeeklyDigest}
              label="Weekly email digest"
              description="Summary of team engagement sent every Monday"
            />
            <Toggle
              checked={showAnalytics}
              onChange={setShowAnalytics}
              label="Show analytics section"
              description="Display engagement chart and week-over-week table on dashboard"
            />
            <Toggle
              checked={compactCards}
              onChange={setCompactCards}
              label="Compact team cards"
              description="Reduce padding on team cards for denser view"
            />
          </div>

          {/* About */}
          {section('About')}
          <div style={{
            padding: '12px 16px', background: '#EAF2EC',
            borderRadius: 12, border: `1px solid ${T.border}`,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
              <span style={{ fontSize: 13, color: T.muted2 }}>Product</span>
              <span style={{ fontSize: 13, fontWeight: 600, color: T.primary }}>AthFuelPath Coach</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
              <span style={{ fontSize: 13, color: T.muted2 }}>Version</span>
              <span style={{ fontSize: 13, fontWeight: 600, color: T.primary }}>1.0 · Beta</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ fontSize: 13, color: T.muted2 }}>Support</span>
              <span style={{ fontSize: 13, fontWeight: 600, color: '#1E5A45' }}>support@athfuelpath.com</span>
            </div>
          </div>

          {/* Sign out */}
          {section('Account')}
          <button
            onClick={() => { onLogout(); onClose() }}
            style={{
              width: '100%', padding: '12px 0',
              background: '#FFF4DD', border: '1px solid #fde5a0',
              color: '#B86600', fontWeight: 700, fontSize: 14,
              borderRadius: 10, cursor: 'pointer',
            }}
          >
            Sign out
          </button>

        </div>
      </div>
    </div>
  )
}

// ── Gear button (reused across nav tiers) ─────────────────────────────────────

function GearBtn({ onClick, small }) {
  return (
    <button
      onClick={onClick}
      aria-label="Open settings"
      title="Settings"
      style={{
        background: 'none', border: 'none', cursor: 'pointer',
        color: 'rgba(255,255,255,0.4)', fontSize: small ? 16 : 18,
        lineHeight: 1, padding: 6,
        transition: 'color .15s',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
    >⚙</button>
  )
}

// ── NavItems ──────────────────────────────────────────────────────────────────

function NavItems({ activeView, hasTeam, callbacks, onNav }) {
  return NAV.map(item => {
    if (item.requiresTeam && !hasTeam) return null
    const active  = activeView === item.key
    const handler = navHandler(item.key, callbacks)
    const action  = () => { handler?.(); onNav?.() }

    return (
      <div key={item.key} style={{ position: 'relative' }}>
        {active && (
          <div style={{
            position: 'absolute', left: 0, top: '50%', transform: 'translateY(-50%)',
            width: 3, height: 20, background: T.lime, borderRadius: '0 3px 3px 0',
          }} />
        )}
        <button
          onClick={action}
          style={{
            display: 'flex', alignItems: 'center', gap: 12,
            padding: '10px 18px 10px 16px', marginInline: 8, borderRadius: 8,
            color: active ? '#fff' : T.muted,
            background: active ? 'rgba(203,234,88,0.13)' : 'none',
            border: 'none', cursor: 'pointer',
            width: 'calc(100% - 16px)', textAlign: 'left',
            fontSize: 14, fontWeight: active ? 600 : 500,
            transition: 'background .1s',
          }}
        >
          <span style={{
            fontSize: 16, width: 22, textAlign: 'center', flexShrink: 0,
            color: active ? T.lime : 'rgba(255,255,255,0.4)',
          }}>{item.icon}</span>
          {item.label}
        </button>
      </div>
    )
  })
}

// ── Sidebar (1440px+) ─────────────────────────────────────────────────────────

function Sidebar({ activeView, onDashboard, onRoster, onReports, onLogout, hasTeam, coachName, onSettings }) {
  return (
    <aside className="nav-sidebar" style={{
      width: W, flexShrink: 0, background: T.sidebar,
      display: 'flex', flexDirection: 'column',
      position: 'fixed', top: 0, left: 0, bottom: 0,
      zIndex: 100, borderRight: '1px solid rgba(255,255,255,0.06)',
    }}>
      <div style={{
        padding: '20px 20px 18px', borderBottom: '1px solid rgba(255,255,255,0.07)',
        display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0,
      }}>
        <div style={{
          width: 32, height: 32, background: T.lime, borderRadius: 8,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 16, fontWeight: 800, color: T.sidebar, flexShrink: 0,
        }}>F</div>
        <div>
          <div style={{ color: '#fff', fontWeight: 700, fontSize: 16, lineHeight: 1.2 }}>AthFuelPath Coach</div>
          <div style={{ color: T.muted, fontSize: 11, fontWeight: 500 }}>Team Dashboard</div>
        </div>
      </div>

      <nav style={{ flex: 1, padding: '10px 0', overflowY: 'auto' }}>
        <div style={{
          fontSize: 10, fontWeight: 700, color: T.mutedLo,
          textTransform: 'uppercase', letterSpacing: '.1em', padding: '14px 20px 6px',
        }}>Navigation</div>
        <NavItems activeView={activeView} hasTeam={hasTeam}
          callbacks={{ onDashboard, onRoster, onReports }} />
      </nav>

      <div style={{ padding: '12px 16px 14px', borderTop: '1px solid rgba(255,255,255,0.07)', flexShrink: 0 }}>
        {coachName && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
            <div style={{
              width: 34, height: 34, borderRadius: '50%', background: 'rgba(203,234,88,0.15)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 14, fontWeight: 700, color: T.lime, flexShrink: 0,
            }}>{initials(coachName)}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#fff', lineHeight: 1.2,
                            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {coachName}
              </div>
              <div style={{ fontSize: 11, color: T.muted, marginTop: 1 }}>Head Coach</div>
            </div>
            <GearBtn onClick={onSettings} />
          </div>
        )}
        {!coachName && (
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
            <GearBtn onClick={onSettings} />
          </div>
        )}
        <button onClick={onLogout} style={{
          width: '100%', padding: '8px 0', background: 'rgba(255,255,255,0.05)',
          border: '1px solid rgba(255,255,255,0.1)', color: T.muted, cursor: 'pointer',
          fontSize: 13, fontWeight: 500, borderRadius: 7,
        }}>Sign out</button>
      </div>
    </aside>
  )
}

// ── Icon rail (1024–1439px) ───────────────────────────────────────────────────

function IconRail({ activeView, onDashboard, onRoster, onReports, onLogout, hasTeam, coachName, onSettings }) {
  return (
    <aside className="nav-icon-rail" style={{
      width: R, flexShrink: 0, background: T.sidebar,
      flexDirection: 'column', alignItems: 'center',
      position: 'fixed', top: 0, left: 0, bottom: 0,
      zIndex: 100, borderRight: '1px solid rgba(255,255,255,0.06)',
    }}>
      <div style={{
        padding: '16px 0', borderBottom: '1px solid rgba(255,255,255,0.07)',
        width: '100%', display: 'flex', justifyContent: 'center',
      }}>
        <div style={{
          width: 32, height: 32, background: T.lime, borderRadius: 8,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 16, fontWeight: 800, color: T.sidebar,
        }}>F</div>
      </div>

      <nav style={{ flex: 1, padding: '10px 0', width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        {NAV.map(item => {
          if (item.requiresTeam && !hasTeam) return null
          const active  = activeView === item.key
          const handler = navHandler(item.key, { onDashboard, onRoster, onReports })
          return (
            <button key={item.key} onClick={handler} title={item.label} aria-label={item.label} style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3,
              padding: '10px 0', width: 56, borderRadius: 10,
              background: active ? 'rgba(203,234,88,0.13)' : 'none',
              border: 'none', cursor: 'pointer', marginBottom: 2, transition: 'background .1s',
            }}>
              <span style={{ fontSize: 18, color: active ? T.lime : 'rgba(255,255,255,0.4)' }}>{item.icon}</span>
              <span style={{
                fontSize: 9, fontWeight: 600, letterSpacing: '.04em', textTransform: 'uppercase',
                color: active ? T.lime : 'rgba(255,255,255,0.3)',
              }}>{item.label}</span>
            </button>
          )
        })}
      </nav>

      <div style={{
        padding: '12px 0 14px', borderTop: '1px solid rgba(255,255,255,0.07)',
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8,
      }}>
        <GearBtn onClick={onSettings} small />
        <div style={{
          width: 34, height: 34, borderRadius: '50%', background: 'rgba(203,234,88,0.15)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 13, fontWeight: 700, color: T.lime, cursor: 'pointer',
        }} onClick={onLogout} title="Sign out" aria-label="Sign out">
          {initials(coachName)}
        </div>
      </div>
    </aside>
  )
}

// ── Top bar + Drawer (<1024px) ────────────────────────────────────────────────

function TopBarAndDrawer({ activeView, onDashboard, onRoster, onReports, onLogout, hasTeam, coachName, onSettings }) {
  const [open, setOpen] = useState(false)
  const close = () => setOpen(false)

  useEffect(() => {
    if (!open) return
    const handler = e => { if (e.key === 'Escape') close() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open])

  return (
    <>
      <header className="nav-top-bar" style={{
        position: 'fixed', top: 0, left: 0, right: 0, height: 56,
        background: T.sidebar, zIndex: 100,
        borderBottom: '1px solid rgba(255,255,255,0.07)',
        alignItems: 'center', justifyContent: 'space-between',
        padding: '0 16px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 28, height: 28, background: T.lime, borderRadius: 7,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 14, fontWeight: 800, color: T.sidebar,
          }}>F</div>
          <span style={{ color: '#fff', fontWeight: 700, fontSize: 15 }}>AthFuelPath Coach</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <GearBtn onClick={onSettings} />
          <button onClick={() => setOpen(true)} aria-label="Open navigation" style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: '#fff', fontSize: 22, lineHeight: 1, padding: 6,
          }}>☰</button>
        </div>
      </header>

      <div className={`nav-drawer-overlay${open ? ' open' : ''}`} onClick={close} aria-hidden="true" />

      <aside className={`nav-drawer${open ? ' open' : ''}`} style={{ background: T.sidebar, display: 'flex', flexDirection: 'column' }} aria-label="Navigation">
        <div style={{
          padding: '16px 20px', borderBottom: '1px solid rgba(255,255,255,0.07)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 28, height: 28, background: T.lime, borderRadius: 7,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 14, fontWeight: 800, color: T.sidebar,
            }}>F</div>
            <span style={{ color: '#fff', fontWeight: 700, fontSize: 15 }}>AthFuelPath Coach</span>
          </div>
          <button onClick={close} aria-label="Close navigation" style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: T.muted, fontSize: 18, lineHeight: 1, padding: 4,
          }}>✕</button>
        </div>

        <nav style={{ flex: 1, padding: '10px 0', overflowY: 'auto' }}>
          <NavItems activeView={activeView} hasTeam={hasTeam}
            callbacks={{ onDashboard, onRoster, onReports }}
            onNav={close} />
        </nav>

        <div style={{ padding: '12px 16px 14px', borderTop: '1px solid rgba(255,255,255,0.07)' }}>
          {coachName && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
              <div style={{
                width: 34, height: 34, borderRadius: '50%', background: 'rgba(203,234,88,0.15)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 14, fontWeight: 700, color: T.lime, flexShrink: 0,
              }}>{initials(coachName)}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: '#fff', lineHeight: 1.2 }}>{coachName}</div>
                <div style={{ fontSize: 11, color: T.muted, marginTop: 1 }}>Head Coach</div>
              </div>
              <GearBtn onClick={() => { onSettings(); close() }} />
            </div>
          )}
          <button onClick={() => { onLogout(); close() }} style={{
            width: '100%', padding: '8px 0', background: 'rgba(255,255,255,0.05)',
            border: '1px solid rgba(255,255,255,0.1)', color: T.muted, cursor: 'pointer',
            fontSize: 13, fontWeight: 500, borderRadius: 7,
          }}>Sign out</button>
        </div>
      </aside>
    </>
  )
}

// ── AppShell ──────────────────────────────────────────────────────────────────

export default function AppShell({ activeView, onDashboard, onRoster, onReports, onLogout, hasTeam, coachName, children }) {
  const [settingsOpen, setSettingsOpen] = useState(false)

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>

      <Sidebar
        activeView={activeView} onDashboard={onDashboard} onRoster={onRoster}
        onReports={onReports} onLogout={onLogout} hasTeam={hasTeam}
        coachName={coachName} onSettings={() => setSettingsOpen(true)}
      />

      <IconRail
        activeView={activeView} onDashboard={onDashboard} onRoster={onRoster}
        onReports={onReports} onLogout={onLogout} hasTeam={hasTeam}
        coachName={coachName} onSettings={() => setSettingsOpen(true)}
      />

      <TopBarAndDrawer
        activeView={activeView} onDashboard={onDashboard} onRoster={onRoster}
        onReports={onReports} onLogout={onLogout} hasTeam={hasTeam}
        coachName={coachName} onSettings={() => setSettingsOpen(true)}
      />

      <main className="main-content" style={{
        marginLeft: W, flex: 1, background: '#F7F5ED', minHeight: '100vh',
      }}>
        {children}
      </main>

      {settingsOpen && (
        <SettingsModal
          coachName={coachName}
          onClose={() => setSettingsOpen(false)}
          onLogout={onLogout}
        />
      )}

    </div>
  )
}

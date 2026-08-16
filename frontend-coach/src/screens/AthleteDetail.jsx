import React, { useEffect, useState } from 'react'
import { fetchAthleteDetail } from '../api.js'

const T = {
  bg:        '#F7F5ED',
  primary:   '#17231D',
  muted:     '#65716B',
  surface:   '#FFFFFF',
  border:    '#DCE4DE',
  lime:      '#CBEA58',
  success:   '#1E5A45',
  successBg: '#EAF2EC',
  attn:      '#B86600',
  attnBg:    '#FFF4DD',
}

function makeInitials(name) {
  if (!name) return '?'
  const words = name.trim().split(/\s+/)
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase()
  return (words[0][0] + words[words.length - 1][0]).toUpperCase()
}

function fmtDate(iso) {
  if (!iso) return null
  const d = new Date(iso + 'T12:00:00')
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function fmtJoined(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function daysAgo(iso) {
  if (!iso) return null
  const then = new Date(iso + 'T12:00:00')
  const now  = new Date()
  const diff = Math.floor((now - then) / 86400000)
  if (diff === 0) return 'Today'
  if (diff === 1) return 'Yesterday'
  return `${diff} days ago`
}

// ── Mini bar ──────────────────────────────────────────────────────────────────

function MiniBar({ pct, color }) {
  return (
    <div style={{ height: 5, background: T.border, borderRadius: 3, overflow: 'hidden', marginTop: 5, width: '100%' }}>
      <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: 3, transition: 'width .4s ease' }} />
    </div>
  )
}

// ── Stat row ──────────────────────────────────────────────────────────────────

function StatRow({ icon, label, value, valueColor, bar, last }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '11px 0',
      borderBottom: last ? 'none' : `1px solid ${T.border}`,
      gap: 12,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, minWidth: 0 }}>
        <span style={{ fontSize: 15, lineHeight: 1, flexShrink: 0 }}>{icon}</span>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontSize: 13, color: T.muted, fontWeight: 500 }}>{label}</div>
          {bar && <MiniBar pct={bar.pct} color={bar.color} />}
        </div>
      </div>
      <div style={{ fontSize: 15, fontWeight: 700, color: valueColor || T.primary, flexShrink: 0, textAlign: 'right' }}>
        {value}
      </div>
    </div>
  )
}

// ── Shimmer ───────────────────────────────────────────────────────────────────

function ShimmerStats() {
  return (
    <div style={{ background: T.surface, borderRadius: 14, border: `1px solid ${T.border}`, padding: '16px 20px' }}>
      {[0,1,2,3,4,5].map(i => (
        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '11px 0', borderBottom: i < 5 ? `1px solid ${T.border}` : 'none' }}>
          <div className="shimmer" style={{ height: 13, width: '40%', borderRadius: 4 }} />
          <div className="shimmer" style={{ height: 13, width: '20%', borderRadius: 4 }} />
        </div>
      ))}
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────

export default function AthleteDetail({ team, athlete: athleteStub, onBack }) {
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]   = useState(null)

  useEffect(() => {
    fetchAthleteDetail(team.id, athleteStub.athlete_id)
      .then(d => { setDetail(d); setLoading(false) })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [team.id, athleteStub.athlete_id])

  const name   = detail?.first_name || athleteStub.first_name || '—'
  const status = detail?.logging_status
  const good   = status === 'active'

  const pct7  = detail ? Math.min(100, Math.round((detail.days_logged_7d  / 7)  * 100)) : 0
  const pct30 = detail ? Math.min(100, Math.round((detail.days_logged_30d / 30) * 100)) : 0
  const color7  = pct7  >= 60 ? T.success : pct7  > 0 ? T.attn : T.border
  const color30 = pct30 >= 60 ? T.success : pct30 > 0 ? T.attn : T.border

  const lastAgo  = daysAgo(detail?.last_logged_at)
  const lastDate = fmtDate(detail?.last_logged_at)
  const lastValue = lastAgo ? (lastDate ? `${lastAgo} · ${lastDate}` : lastAgo) : 'No logs yet'
  const lastColor = lastAgo === 'Today' || lastAgo === 'Yesterday' ? T.success : lastAgo ? T.primary : T.muted

  return (
    <div style={{
      minHeight: '100vh', background: T.bg,
    }}>
      <div className="roster-wrap">

        {/* Header */}
        <header style={{ marginBottom: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <button
              onClick={onBack}
              aria-label="Back to roster"
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                color: T.muted, fontSize: 26, lineHeight: 1,
                padding: '10px 10px 10px 0',
                minWidth: 44, minHeight: 44,
                display: 'flex', alignItems: 'center', justifyContent: 'flex-start',
                flexShrink: 0,
              }}
            >‹</button>
            <h1 style={{ fontWeight: 700, fontSize: 28, color: T.primary, lineHeight: 1.1, margin: 0 }}>
              {name}
            </h1>
          </div>
        </header>

        {/* Identity + stats: one card */}
        {!loading && !error && detail && (
          <div style={{
            background: T.surface,
            border: `1px solid ${T.border}`,
            borderRadius: 16,
            boxShadow: '0 1px 6px rgba(0,0,0,.06)',
            overflow: 'hidden',
          }}>

            {/* Identity strip */}
            <div style={{
              display: 'flex', alignItems: 'center', gap: 14,
              padding: '16px 20px',
              borderBottom: `1px solid ${T.border}`,
              background: good ? T.successBg : status === 'inactive' ? T.attnBg : '#f9f9f9',
            }}>
              <div style={{
                width: 42, height: 42, borderRadius: '50%', flexShrink: 0,
                background: good ? '#d0f0db' : '#e8e8e8',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 15, fontWeight: 700, color: good ? T.success : T.muted,
                userSelect: 'none',
              }}>
                {makeInitials(name)}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 14, color: T.primary, fontWeight: 600 }}>
                  {[detail.age && `${detail.age} yrs`, detail.gender, detail.position].filter(Boolean).join(' · ')}
                </div>
                {detail.competition_level && (
                  <div style={{ fontSize: 12, color: T.muted, marginTop: 1 }}>{detail.competition_level}</div>
                )}
              </div>
              <span style={{
                display: 'inline-flex', alignItems: 'center', gap: 5,
                background: good ? '#d0f0db' : status === 'inactive' ? '#fde5a0' : '#e8e8e8',
                color: good ? T.success : status === 'inactive' ? T.attn : T.muted,
                fontSize: 12, fontWeight: 600, padding: '4px 10px', borderRadius: 20,
                border: `1px solid ${good ? '#aee0be' : status === 'inactive' ? '#f5cb6b' : T.border}`,
                flexShrink: 0,
              }}>
                {good ? '● Active' : status === 'inactive' ? '○ No recent activity' : '○ Not in app'}
              </span>
            </div>

            {/* Stat rows */}
            <div style={{ padding: '0 20px' }}>
              <StatRow icon="🔥" label="Current streak"    value={`${detail.current_streak} day${detail.current_streak !== 1 ? 's' : ''}`}          valueColor={detail.current_streak > 0 ? T.success : T.muted} />
              <StatRow icon="⭐" label="Best streak"       value={`${detail.best_streak} day${detail.best_streak !== 1 ? 's' : ''}`}                 valueColor={detail.best_streak > 0 ? T.primary : T.muted} />
              <StatRow icon="📅" label="This week"         value={`${detail.days_logged_7d} / 7 days`}   valueColor={color7}  bar={{ pct: pct7,  color: color7  }} />
              <StatRow icon="📆" label="Last 30 days"      value={`${detail.days_logged_30d} / 30 days`} valueColor={color30} bar={{ pct: pct30, color: color30 }} />
              <StatRow icon="📊" label="Total days logged" value={`${detail.total_days_logged} day${detail.total_days_logged !== 1 ? 's' : ''}`}     valueColor={T.primary} />
              <StatRow icon="🕐" label="Last logged"       value={lastValue} valueColor={lastColor} last />
            </div>

            {/* Joined footer */}
            {detail.joined_at && (
              <div style={{
                borderTop: `1px solid ${T.border}`,
                padding: '10px 20px',
                fontSize: 12, color: T.muted, fontStyle: 'italic',
              }}>
                Joined AthFuelPath {fmtJoined(detail.joined_at)}
              </div>
            )}
          </div>
        )}

        {/* Loading */}
        {loading && <ShimmerStats />}

        {/* Error */}
        {!loading && error && (
          <p style={{ color: T.muted, fontSize: 15, textAlign: 'center', marginTop: 40 }}>
            Couldn't load athlete data.
          </p>
        )}

        {/* Disclaimer */}
        {!loading && detail && (
          <p style={{ fontSize: 12, color: T.muted, marginTop: 14, fontStyle: 'italic', lineHeight: 1.5 }}>
            Metrics reflect app logging activity only — not verified nutrition intake.
          </p>
        )}

      </div>
    </div>
  )
}

import React, { useState } from 'react'
import { login } from '../api.js'

const T = {
  pageBg:    '#EDE9DF',
  darkGreen: '#123D2F',
  lime:      '#CBEA58',
  primary:   '#17231D',
  muted:     '#65716B',
  surface:   '#FFFFFF',
  border:    '#DCE4DE',
  error:     '#C0392B',
}

// Organic blob shapes — purely decorative, aria-hidden
function Blob({ style }) {
  return <div aria-hidden="true" style={{ position: 'absolute', pointerEvents: 'none', ...style }} />
}

const s = {
  page: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: T.pageBg,
    overflow: 'hidden',
    position: 'relative',
    padding: '40px 20px',
  },
  card: {
    background: T.surface,
    borderRadius: 20,
    padding: '40px 36px',
    width: '100%',
    maxWidth: 400,
    border: `1px solid rgba(220,228,222,0.8)`,
    boxShadow: '0 4px 24px rgba(23, 35, 29, 0.08)',
    position: 'relative',
    zIndex: 1,
  },
  logoRow: { display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 },
  logoMark: {
    width: 38, height: 38, background: T.darkGreen, borderRadius: 10,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontSize: 17, fontWeight: 800, color: T.lime,
  },
  brand: { fontWeight: 800, fontSize: 20, color: T.primary },
  sub:   { color: T.muted, fontSize: 14, marginBottom: 32, lineHeight: 1.5 },
  label: { display: 'block', fontSize: 13, fontWeight: 600, color: T.primary, marginBottom: 6 },
  input: {
    width: '100%', padding: '12px 14px',
    border: `1.5px solid ${T.border}`, borderRadius: 10,
    fontSize: 15, outline: 'none', marginBottom: 16,
    fontFamily: 'inherit', background: T.surface, color: T.primary,
    transition: 'border-color .15s',
    boxSizing: 'border-box',
  },
  btn: {
    width: '100%', padding: '14px 0',
    background: T.darkGreen, color: T.lime,
    border: 'none', borderRadius: 12,
    fontSize: 15, fontWeight: 700, cursor: 'pointer',
    marginTop: 4, letterSpacing: '.02em',
    boxShadow: '0 4px 16px rgba(18, 61, 47, 0.2)',
    transition: 'opacity .15s',
  },
  err: { color: T.error, fontSize: 13, marginTop: 12, textAlign: 'center' },
}

export default function Login({ onLogin }) {
  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [error, setError]       = useState('')
  const [loading, setLoading]   = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await login(email, password)
      onLogin(data)
    } catch (err) {
      setError(err.message || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={s.page}>
      {/* ── Decorative background blobs ── */}
      {/* Top-left large organic shape */}
      <Blob style={{
        width: 620, height: 560,
        top: -160, left: -160,
        background: 'radial-gradient(ellipse at 40% 40%, rgba(180,215,150,0.38) 0%, rgba(160,200,130,0.18) 45%, transparent 72%)',
        borderRadius: '62% 38% 54% 46% / 48% 62% 38% 52%',
        transform: 'rotate(-15deg)',
      }} />
      {/* Top-right accent */}
      <Blob style={{
        width: 420, height: 380,
        top: -80, right: -100,
        background: 'radial-gradient(ellipse at 55% 45%, rgba(190,220,155,0.30) 0%, rgba(170,210,140,0.12) 50%, transparent 72%)',
        borderRadius: '45% 55% 38% 62% / 55% 42% 58% 45%',
        transform: 'rotate(20deg)',
      }} />
      {/* Bottom-left subtle organic */}
      <Blob style={{
        width: 340, height: 300,
        bottom: -80, left: -60,
        background: 'radial-gradient(ellipse at 45% 50%, rgba(140,185,110,0.22) 0%, transparent 65%)',
        borderRadius: '50% 50% 40% 60% / 60% 40% 60% 40%',
        transform: 'rotate(10deg)',
      }} />
      {/* Bottom-right faint wash */}
      <Blob style={{
        width: 280, height: 260,
        bottom: -60, right: -40,
        background: 'radial-gradient(ellipse at 50% 50%, rgba(200,228,170,0.20) 0%, transparent 65%)',
        borderRadius: '55% 45% 60% 40% / 45% 60% 40% 55%',
      }} />

      {/* ── Login card ── */}
      <div style={s.card}>
        <div style={s.logoRow}>
          <div style={s.logoMark}>F</div>
          <span style={s.brand}>AthFuelPath Coach</span>
        </div>
        <div style={s.sub}>Coach dashboard · Sign in to continue</div>
        <form onSubmit={handleSubmit}>
          <label style={s.label}>Email</label>
          <input style={s.input} type="email" value={email}
                 onChange={e => setEmail(e.target.value)} required autoFocus />
          <label style={s.label}>Password</label>
          <input style={s.input} type="password" value={password}
                 onChange={e => setPassword(e.target.value)} required />
          <button style={{ ...s.btn, opacity: loading ? 0.7 : 1 }} type="submit" disabled={loading}>
            {loading ? 'Signing in…' : 'Sign In'}
          </button>
          {error && <div style={s.err}>{error}</div>}
        </form>
      </div>
    </div>
  )
}

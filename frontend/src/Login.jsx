import { useState, useEffect, useRef } from "react";

const API = import.meta.env.VITE_API_URL ?? "";

const FEATURES = [
  { icon: "🧠", title: "AI Nutrition Blueprints", desc: "Personalized plans built around each athlete's age, position, game schedule, and dietary needs." },
  { icon: "📅", title: "Game-Day Fuel Protocols", desc: "Exact meals and timing for pre-game, halftime, and recovery — never guess again." },
  { icon: "📊", title: "Live Macro Tracking", desc: "Log meals and watch real-time dials update against science-backed daily targets." },
  { icon: "💧", title: "Hydration Calculator", desc: "Sweat-rate estimates based on age, competition level, and weather conditions." },
];

// screen: "welcome" | "who" | "create" | "signin"
export default function Login({ onLogin, onNewAccount }) {
  const [screen, setScreen]           = useState("welcome");
  const [selectedRole, setSelectedRole] = useState(null); // "parent" | "athlete"
  const [email, setEmail]             = useState("");
  const [loading, setLoading]         = useState(false);
  const [error, setError]             = useState("");
  const [socialMsg, setSocialMsg]     = useState("");
  const [isMobile, setIsMobile]       = useState(window.innerWidth < 700);

  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth < 700);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  // Prevent the popstate handler from triggering another pushState
  const isPoppingRef = useRef(false);

  // Push a history entry whenever the screen changes
  useEffect(() => {
    if (!isPoppingRef.current) {
      window.history.pushState({ loginScreen: screen }, "");
    }
    isPoppingRef.current = false;
  }, [screen]);

  // Handle browser/phone back button
  useEffect(() => {
    function onPop(e) {
      const s = e.state?.loginScreen || "welcome";
      isPoppingRef.current = true;
      setScreen(s);
      setError("");
      setSocialMsg("");
    }
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  function go(s) {
    setError("");
    setSocialMsg("");
    setScreen(s);
  }

  async function handleLogin(e) {
    e.preventDefault();
    if (!email.trim()) return setError("Please enter your email address.");
    if (email.trim().toLowerCase() === "test@gmail.com") { onNewAccount(); return; }
    setLoading(true); setError("");
    try {
      const res = await fetch(`${API}/api/parents/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim().toLowerCase() }),
      });
      if (res.status === 404) { setError("No account found with that email. Create a new account to get started."); return; }
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "Something went wrong. Please try again.");
      }
      const data = await res.json();
      onLogin(data);
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }

  function handleSocial(provider) {
    setSocialMsg(`${provider} sign-in is coming soon — use email for now.`);
    setTimeout(() => setSocialMsg(""), 3500);
  }

  // ─────────────────────────────────────────────────────────────────────
  // SIGN IN — two-column layout, existing experience preserved exactly
  // ─────────────────────────────────────────────────────────────────────
  if (screen === "signin") {
    return (
      <div style={s.wrapper}>
        {/* Left: hero — hidden on mobile */}
        {!isMobile && (
          <div style={s.hero}>
            <div style={s.wordmark}>⚽ AthFuelPath<span style={s.wordmarkYouth}>Youth</span></div>
            <h1 style={s.headline}>
              The Complete Sports Performance platform for every competitive soccer Athlete
            </h1>
            <p style={s.subheadline}>
              AI-generated, RD-approved Nutrition Blueprints — personalized to every athlete's age,
              training schedule, game days, dietary needs, and performance goals.
              Built for youth soccer clubs, ages&nbsp;9–17.
            </p>
            <div style={s.features}>
              {FEATURES.map(f => (
                <div key={f.title} style={s.featureCard}>
                  <div style={s.featureIcon}>{f.icon}</div>
                  <div>
                    <div style={s.featureTitle}>{f.title}</div>
                    <div style={s.featureDesc}>{f.desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Right: sign-in card — full width on mobile */}
        <div style={{ ...s.panel, ...(isMobile ? s.panelMobile : {}) }}>
          <div style={s.card}>
            <div style={s.cardLogo}>⚽ AthFuelPath</div>
            <h2 style={s.cardTitle}>Welcome back</h2>
            <p style={s.cardDesc}>Sign in with your parent or guardian account.</p>

            <form onSubmit={handleLogin}>
              <label style={s.label}>Parent or Guardian Email</label>
              <input
                style={s.input}
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={e => { setEmail(e.target.value); setError(""); }}
                autoFocus
              />
              {error && <p style={s.error}>{error}</p>}
              <button style={s.primaryBtn} type="submit" disabled={loading}>
                {loading ? "Signing in…" : "Sign In →"}
              </button>
            </form>

            <p style={s.disclaimer}>
              AthFuelPath provides educational food guidance — not medical nutrition therapy.
            </p>
          </div>
        </div>
      </div>
    );
  }

  // ─────────────────────────────────────────────────────────────────────
  // CENTERED LAYOUT — welcome, who, create
  // ─────────────────────────────────────────────────────────────────────
  return (
    <div style={s.wrapper}>
      <div style={s.centerWrap}>

        {/* ── SCREEN 1: Welcome / Value Proposition ── */}
        {screen === "welcome" && (
          <div style={s.cCard} key="welcome">
            <div style={s.cLogo}>⚽ <span style={s.cLogoGreen}>AthFuelPath</span></div>

            <h1 style={s.bigHeadline}>Fuel your game.</h1>
            <p style={s.heroSub}>
              Smart fueling, synced to your athlete's daily schedule — built by a sports dietitian mom who's lived this journey to D1.<br /><br />
              Nutrient timing, meal plans, and hydration for every practice, game, and tournament.
            </p>

            <button style={s.primaryBtn} onClick={() => go("who")}>
              Get Started →
            </button>
            <p style={s.centerNote}>
              Already have an account?{" "}
              <button style={s.inlineLink} onClick={() => go("signin")}>Sign In</button>
            </p>
            <p style={s.disclaimer}>
              AthFuelPath provides educational food guidance — not medical nutrition therapy.
            </p>
          </div>
        )}

        {/* ── SCREEN 2: Who is setting up AthFuelPath? ── */}
        {screen === "who" && (
          <div style={s.cCard} key="who">
            <button style={s.backBtn} onClick={() => { go("welcome"); setSelectedRole(null); }}>
              ← Back
            </button>
            <div style={s.cLogo}>⚽ <span style={s.cLogoGreen}>AthFuelPath</span></div>

            <h2 style={s.screenHeading}>Who is setting up AthFuelPath?</h2>
            <p style={s.screenSub}>
              We'll personalize the experience based on who's using the app.
            </p>

            <div style={s.roleRow}>
              {[
                { id: "parent",  emoji: "👨‍👩‍👧", title: "Parent / Guardian", desc: "I manage my athlete's nutrition and profile." },
                { id: "athlete", emoji: "⚽",     title: "Athlete",           desc: "I'm a soccer player using AthFuelPath with my family." },
              ].map(r => (
                <button
                  key={r.id}
                  style={{ ...s.roleBtn, ...(selectedRole === r.id ? s.roleBtnOn : {}) }}
                  onClick={() => setSelectedRole(r.id)}
                >
                  {selectedRole === r.id && <div style={s.checkMark}>✓</div>}
                  <span style={s.roleEmoji}>{r.emoji}</span>
                  <span style={s.roleTitle}>{r.title}</span>
                  <span style={s.roleDesc}>{r.desc}</span>
                </button>
              ))}
            </div>

            {selectedRole === "athlete" && (
              <div style={s.infoBox}>
                <span style={{ fontSize: "21px", flexShrink: 0, lineHeight: 1 }}>ℹ️</span>
                <p style={s.infoText}>
                  AthFuelPath is built for young athletes, but a parent or guardian needs to create
                  the main account first.
                </p>
              </div>
            )}

            {selectedRole === "athlete" ? (
              <>
                <button style={s.primaryBtn} onClick={() => handleSocial("Invite")}>
                  Invite Parent / Guardian →
                </button>
                <p style={s.centerNote}>
                  <button style={s.inlineLink} onClick={() => go("signin")}>
                    My parent already has an account
                  </button>
                </p>
              </>
            ) : (
              <button
                style={{
                  ...s.primaryBtn,
                  opacity: selectedRole === "parent" ? 1 : 0.42,
                  cursor:  selectedRole === "parent" ? "pointer" : "default",
                }}
                onClick={() => selectedRole === "parent" && go("create")}
              >
                Continue →
              </button>
            )}
          </div>
        )}

        {/* ── SCREEN 3: Create Account ── */}
        {screen === "create" && (
          <div style={s.cCard} key="create">
            <button style={s.backBtn} onClick={() => go("who")}>← Back</button>
            <div style={s.cLogo}>⚽ <span style={s.cLogoGreen}>AthFuelPath</span></div>

            <h2 style={s.screenHeading}>Create your AthFuelPath account</h2>
            <p style={s.screenSub}>
              Use a parent or guardian account to safely manage your athlete's experience.
            </p>

            {socialMsg && <div style={s.socialToast}>{socialMsg}</div>}

            <button style={s.googleBtn} onClick={() => handleSocial("Google")}>
              <span style={s.gIcon}>G</span>
              Continue with Google
            </button>
            <button style={s.appleBtn} onClick={() => handleSocial("Apple")}>
              <span style={s.appleIcon}></span>
              Continue with Apple
            </button>

            <div style={s.divider}>
              <div style={s.dividerLine} />
              <span style={s.dividerText}>or</span>
              <div style={s.dividerLine} />
            </div>

            <button style={s.outlineBtn} onClick={onNewAccount}>
              Continue with Email
            </button>

            <p style={s.centerNote}>
              Already have an account?{" "}
              <button style={s.inlineLink} onClick={() => go("signin")}>Sign In</button>
            </p>
            <p style={s.disclaimer}>
              AthFuelPath provides educational food guidance — not medical nutrition therapy.
            </p>
          </div>
        )}

      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Styles
// ─────────────────────────────────────────────────────────────────────────────
const s = {

  // ── Shared background ──────────────────────────────────────────────────────
  wrapper: {
    minHeight: "100vh",
    background: "linear-gradient(145deg, #1b4332 0%, #2d6a4f 50%, #3a7d60 100%)",
    display: "flex",
    alignItems: "stretch",
    fontFamily: "'Nunito', 'DM Sans', sans-serif",
  },

  // ── Centered layout (welcome / who / create) ───────────────────────────────
  centerWrap: {
    flex: 1,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "24px 16px",
  },
  cCard: {
    background: "#ffffff",
    borderRadius: "24px",
    padding: "32px 24px",
    width: "100%",
    maxWidth: "440px",
    boxSizing: "border-box",
    boxShadow: "0 24px 64px rgba(13,35,24,0.30)",
    border: "1px solid #dce8e0",
    animation: "fadeUp 0.32s ease",
  },
  cLogo: {
    fontSize: "25px",
    fontWeight: "900",
    color: "#2d6a4f",
    textAlign: "center",
    marginBottom: "26px",
    fontFamily: "'Nunito', sans-serif",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "5px",
  },
  cLogoGreen: {
    color: "#2d6a4f",
  },

  // Welcome screen
  bigHeadline: {
    fontSize: "clamp(34px, 6vw, 42px)",
    fontWeight: "900",
    color: "#1b3a2a",
    textAlign: "center",
    letterSpacing: "-0.04em",
    lineHeight: 1.1,
    marginBottom: "14px",
    fontFamily: "'Nunito', sans-serif",
  },
  heroSub: {
    fontSize: "20px",
    fontWeight: "600",
    color: "#2d6a4f",
    textAlign: "center",
    lineHeight: 1.55,
    marginBottom: "14px",
  },
  heroBody: {
    fontSize: "18px",
    color: "#4a6358",
    textAlign: "center",
    lineHeight: 1.65,
    marginBottom: "28px",
  },

  // Screen 2 / 3 headings
  screenHeading: {
    fontSize: "27px",
    fontWeight: "800",
    color: "#1b3a2a",
    textAlign: "center",
    letterSpacing: "-0.02em",
    lineHeight: 1.2,
    marginBottom: "8px",
    fontFamily: "'Nunito', sans-serif",
  },
  screenSub: {
    fontSize: "18px",
    color: "#4a6358",
    textAlign: "center",
    lineHeight: 1.6,
    marginBottom: "24px",
  },

  // Role selector
  roleRow: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: "12px",
    marginBottom: "18px",
  },
  roleBtn: {
    background: "#f4f8f5",
    border: "2px solid #dce8e0",
    borderRadius: "16px",
    padding: "18px 12px 14px",
    cursor: "pointer",
    textAlign: "center",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: "5px",
    position: "relative",
    transition: "border-color 0.15s, background 0.15s",
    fontFamily: "'Nunito', sans-serif",
  },
  roleBtnOn: {
    background: "rgba(45,106,79,0.06)",
    border: "2px solid #2d6a4f",
  },
  roleEmoji: {
    fontSize: "33px",
    display: "block",
    marginBottom: "4px",
  },
  roleTitle: {
    fontSize: "17px",
    fontWeight: "800",
    color: "#1b3a2a",
    lineHeight: 1.2,
    fontFamily: "'Nunito', sans-serif",
    display: "block",
  },
  roleDesc: {
    fontSize: "15px",
    color: "#4a6358",
    lineHeight: 1.4,
    fontFamily: "'DM Sans', sans-serif",
    display: "block",
  },
  checkMark: {
    position: "absolute",
    top: "8px",
    right: "8px",
    width: "20px",
    height: "20px",
    background: "#2d6a4f",
    borderRadius: "50%",
    color: "#fff",
    fontSize: "14px",
    fontWeight: "800",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },

  // Athlete info box
  infoBox: {
    display: "flex",
    gap: "10px",
    alignItems: "flex-start",
    background: "rgba(45,106,79,0.07)",
    border: "1px solid rgba(45,106,79,0.22)",
    borderRadius: "12px",
    padding: "13px 14px",
    marginBottom: "18px",
  },
  infoText: {
    fontSize: "17px",
    color: "#1b3a2a",
    lineHeight: 1.55,
    fontFamily: "'DM Sans', sans-serif",
    margin: 0,
  },

  // Social buttons (create screen)
  socialToast: {
    background: "#f0faf4",
    border: "1px solid #b0e8c8",
    borderRadius: "8px",
    padding: "10px 14px",
    fontSize: "16px",
    color: "#2d6a4f",
    fontFamily: "'DM Sans', sans-serif",
    marginBottom: "14px",
    textAlign: "center",
  },
  googleBtn: {
    width: "100%",
    padding: "13px",
    background: "#ffffff",
    color: "#1b3a2a",
    border: "1.5px solid #dce8e0",
    borderRadius: "10px",
    fontSize: "19px",
    fontWeight: "700",
    fontFamily: "'Nunito', sans-serif",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "10px",
    marginBottom: "10px",
    boxShadow: "0 2px 8px rgba(27,67,50,0.07)",
    transition: "box-shadow 0.15s",
  },
  gIcon: {
    fontSize: "21px",
    fontWeight: "900",
    color: "#4285f4",
    fontFamily: "Arial, sans-serif",
    letterSpacing: "-0.5px",
  },
  appleBtn: {
    width: "100%",
    padding: "13px",
    background: "#1b3a2a",
    color: "#ffffff",
    border: "none",
    borderRadius: "10px",
    fontSize: "19px",
    fontWeight: "700",
    fontFamily: "'Nunito', sans-serif",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "10px",
    marginBottom: "4px",
  },
  appleIcon: {
    fontSize: "22px",
    lineHeight: 1,
  },

  // Back button
  backBtn: {
    background: "none",
    border: "none",
    color: "#4a6358",
    fontSize: "17px",
    fontWeight: "600",
    fontFamily: "'DM Sans', sans-serif",
    cursor: "pointer",
    padding: "0",
    marginBottom: "18px",
    display: "block",
    letterSpacing: "0.01em",
  },

  // Footer links
  centerNote: {
    textAlign: "center",
    fontSize: "17px",
    color: "#4a6358",
    marginTop: "16px",
    fontFamily: "'DM Sans', sans-serif",
    lineHeight: 1.5,
  },
  inlineLink: {
    background: "none",
    border: "none",
    color: "#2d6a4f",
    fontWeight: "700",
    fontSize: "inherit",
    fontFamily: "inherit",
    cursor: "pointer",
    padding: "0",
    textDecoration: "underline",
    textUnderlineOffset: "2px",
  },

  // ── Sign-in layout (two-column, existing) ─────────────────────────────────
  hero: {
    flex: "1 1 0",
    display: "flex",
    flexDirection: "column",
    justifyContent: "center",
    padding: "60px 56px",
    maxWidth: "640px",
    position: "relative",
    overflow: "hidden",
  },
  wordmark: {
    fontSize: "37px",
    fontWeight: "900",
    color: "#ffffff",
    letterSpacing: "-0.5px",
    marginBottom: "20px",
    fontFamily: "'Nunito', sans-serif",
  },
  wordmarkYouth: { color: "#95d5b2", fontWeight: "500", marginLeft: "6px" },
  headline: {
    fontSize: "clamp(26px, 3vw, 38px)",
    fontWeight: "800",
    color: "#ffffff",
    lineHeight: 1.6,
    letterSpacing: "-0.3px",
    margin: "0 0 16px",
    fontFamily: "'Nunito', sans-serif",
  },
  subheadline: {
    fontSize: "20px",
    color: "rgba(183,228,199,0.9)",
    lineHeight: 1.7,
    marginBottom: "32px",
    maxWidth: "500px",
  },
  features: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" },
  featureCard: {
    background: "rgba(255,255,255,0.08)",
    border: "1px solid rgba(255,255,255,0.13)",
    backdropFilter: "blur(4px)",
    borderRadius: "14px",
    padding: "15px",
    display: "flex",
    gap: "10px",
    alignItems: "flex-start",
  },
  featureIcon: { fontSize: "25px", flexShrink: 0, marginTop: "1px" },
  featureTitle: { fontSize: "18px", fontWeight: "700", color: "#ffffff", marginBottom: "3px", fontFamily: "'Nunito', sans-serif" },
  featureDesc: { fontSize: "16px", color: "rgba(183,228,199,0.85)", lineHeight: 1.5 },

  panel: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "40px",
    flexShrink: 0,
    width: "420px",
    background: "#f4f8f5",
  },
  panelMobile: {
    width: "100%",
    padding: "24px 16px",
    alignItems: "flex-start",
  },
  card: {
    background: "#ffffff",
    borderRadius: "20px",
    padding: "36px 32px",
    width: "100%",
    boxShadow: "0 16px 48px rgba(27,67,50,0.14)",
    border: "1px solid #dce8e0",
  },
  cardLogo: {
    fontSize: "25px",
    fontWeight: "900",
    color: "#2d6a4f",
    textAlign: "center",
    marginBottom: "18px",
    fontFamily: "'Nunito', sans-serif",
  },
  cardTitle: {
    fontSize: "27px",
    fontWeight: "800",
    color: "#1b3a2a",
    margin: "0 0 6px",
    textAlign: "center",
    fontFamily: "'Nunito', sans-serif",
  },
  cardDesc: {
    fontSize: "18px",
    color: "#4a6358",
    textAlign: "center",
    lineHeight: 1.6,
    marginBottom: "22px",
  },
  label: {
    display: "block",
    fontSize: "16px",
    fontWeight: "700",
    color: "#4a6358",
    marginBottom: "6px",
    textTransform: "uppercase",
    letterSpacing: "0.06em",
    fontFamily: "'Nunito', sans-serif",
  },
  input: {
    width: "100%",
    padding: "11px 14px",
    border: "1.5px solid #dce8e0",
    borderRadius: "10px",
    fontSize: "20px",
    fontFamily: "'DM Sans', sans-serif",
    outline: "none",
    boxSizing: "border-box",
    marginBottom: "12px",
    background: "#f4f8f5",
    color: "#1b3a2a",
    transition: "border-color 0.2s, box-shadow 0.2s",
  },
  error: { color: "#dc2626", fontSize: "18px", marginBottom: "10px", marginTop: "-6px" },

  // ── Shared buttons ─────────────────────────────────────────────────────────
  primaryBtn: {
    width: "100%",
    padding: "14px",
    background: "linear-gradient(135deg, #2d6a4f, #52b788)",
    color: "#fff",
    border: "none",
    borderRadius: "10px",
    fontSize: "20px",
    fontWeight: "700",
    fontFamily: "'Nunito', sans-serif",
    cursor: "pointer",
    letterSpacing: "0.01em",
    boxShadow: "0 4px 14px rgba(45,106,79,0.28)",
    transition: "opacity 0.2s",
  },
  outlineBtn: {
    width: "100%",
    padding: "13px",
    background: "transparent",
    color: "#2d6a4f",
    border: "1.5px solid #95d5b2",
    borderRadius: "10px",
    fontSize: "19px",
    fontWeight: "700",
    fontFamily: "'Nunito', sans-serif",
    cursor: "pointer",
  },

  divider: { display: "flex", alignItems: "center", margin: "18px 0", gap: "12px" },
  dividerLine: { flex: 1, height: "1px", background: "#dce8e0" },
  dividerText: { fontSize: "17px", color: "#4a6358", padding: "0 4px", flexShrink: 0 },

  footerNote: {
    textAlign: "center",
    fontSize: "17px",
    color: "#4a6358",
    marginTop: "14px",
    fontFamily: "'DM Sans', sans-serif",
  },
  disclaimer: {
    fontSize: "16px",
    color: "#4a6358",
    textAlign: "center",
    marginTop: "20px",
    lineHeight: 1.6,
  },
};

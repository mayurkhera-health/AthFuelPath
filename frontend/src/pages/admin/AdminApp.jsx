import { useEffect, useState } from "react";
import { getToken, clearToken, adminFetch } from "./adminApi";
import { C, FONT_DISPLAY } from "./theme";
import { useIsNarrow } from "./hooks";
import AdminLogin from "./AdminLogin";
import AdminUsersSplit from "./AdminUsersSplit";
import AdminAnalytics from "./AdminAnalytics";
import AdminHealth from "./AdminHealth";
import AdminActionHub from "./AdminActionHub";

// Overall health strip — one fetch per admin page load, no polling.
function HealthStrip({ onOpen }) {
  const [snap, setSnap] = useState(null);
  useEffect(() => {
    let alive = true;
    adminFetch("/health")
      .then((s) => { if (alive) setSnap(s); })
      .catch(() => {}); // strip is best-effort; never block the page
    return () => { alive = false; };
  }, []);
  if (!snap) return null;
  // Founder view: red = something's actually wrong; pending checks never alarm.
  const redCount = snap.checks.filter((c) => c.status === "red").length;
  const meta = redCount > 0
    ? { color: C.danger, bg: C.dangerBg, border: C.dangerBorder, label: `${redCount} ${redCount === 1 ? "issue needs" : "issues need"} attention` }
    : { color: C.brandMid, bg: C.brandGhost, border: C.brandLight, label: "All systems healthy" };
  return (
    <button onClick={onOpen} style={{
      display: "flex", gap: 8, alignItems: "center", width: "100%", cursor: "pointer",
      font: `700 13px ${FONT_DISPLAY}`, color: meta.color, background: meta.bg,
      border: `1px solid ${meta.border}`, borderRadius: 10, padding: "8px 14px", marginBottom: 16,
    }}>
      <span style={{ width: 10, height: 10, borderRadius: "50%", background: meta.color }} />
      System health: {meta.label}
      <span style={{ marginLeft: "auto", color: C.text3, fontWeight: 600 }}>View →</span>
    </button>
  );
}

export default function AdminApp() {
  const [authed, setAuthed] = useState(!!getToken());
  // Default landing = Mission Control (the founder's ops dashboard).
  const [section, setSection] = useState("actionhub"); // actionhub|users|analytics|health
  const [pendingUserId, setPendingUserId] = useState(null); // deep-link a family from the Action Hub
  const mobile = useIsNarrow(768);     // phones/small tablets → top bar + drawer nav
  const [menuOpen, setMenuOpen] = useState(false);

  // Called by child fetches when a 401 (AuthError) bubbles up.
  function onLoggedOut() {
    clearToken();
    setAuthed(false);
  }

  // Action Hub "View" buttons navigate to a section (and optionally a family).
  function navigate(toSection, id) {
    if (id != null) setPendingUserId(id);
    setSection(toSection);
  }

  if (!authed) return <AdminLogin onAuth={() => setAuthed(true)} />;

  const navItem = (key, label) => {
    const active = section === key;
    return (
      <button
        key={key}
        onClick={() => { setSection(key); setMenuOpen(false); }}
        style={{
          display: "block", width: "100%", textAlign: "left", cursor: "pointer",
          font: `${active ? 700 : 600} 14px ${FONT_DISPLAY}`, padding: "11px 14px 11px 16px",
          borderRadius: 10, marginBottom: 4,
          border: "none", borderLeft: `4px solid ${active ? C.sidebarActiveBar : "transparent"}`,
          background: active ? C.sidebarActiveBg : "transparent",
          color: active ? C.sidebarText : C.sidebarInactive,
        }}
      >{label}</button>
    );
  };

  const navItems = (
    <>
      {navItem("actionhub", "Mission Control")}
      {navItem("users", "Users")}
      {navItem("analytics", "Analytics")}
      {navItem("health", "System Health")}
    </>
  );

  const logoutBtn = (
    <button onClick={onLoggedOut} style={{
      font: `600 13px ${FONT_DISPLAY}`, color: C.sidebarInactive, background: "transparent",
      border: `1px solid rgba(255,255,255,0.2)`, borderRadius: 8, padding: "9px 12px", cursor: "pointer",
    }}>Log out</button>
  );

  const pageContent = (
    <>
      {/* Health strip is redundant where a page has its own health line. */}
      {section !== "health" && section !== "actionhub" && (
        <HealthStrip onOpen={() => setSection("health")} />
      )}
      {section === "actionhub" && <AdminActionHub onLoggedOut={onLoggedOut} onNavigate={navigate} />}
      {section === "users" && <AdminUsersSplit onLoggedOut={onLoggedOut} initialSelectedId={pendingUserId} />}
      {section === "analytics" && <AdminAnalytics onLoggedOut={onLoggedOut} />}
      {section === "health" && <AdminHealth onLoggedOut={onLoggedOut} />}
    </>
  );

  // Mobile: sticky top bar + collapsible drawer nav; content stacks full-width.
  if (mobile) {
    return (
      <div style={{ minHeight: "100vh", background: C.bg, font: `400 14px ${FONT_DISPLAY}` }}>
        <header style={{
          position: "sticky", top: 0, zIndex: 20, background: C.sidebarBg,
          display: "flex", alignItems: "center", gap: 14, padding: "12px 16px",
        }}>
          <button
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((o) => !o)}
            style={{
              background: "transparent", border: `1px solid rgba(255,255,255,0.25)`, borderRadius: 8,
              color: C.sidebarText, font: `700 18px ${FONT_DISPLAY}`, lineHeight: 1,
              padding: "6px 13px", cursor: "pointer",
            }}
          >{menuOpen ? "✕" : "☰"}</button>
          <span style={{ font: `800 17px ${FONT_DISPLAY}`, color: C.sidebarText }}>AthFuelPath Admin</span>
        </header>
        {menuOpen && (
          <nav style={{
            position: "sticky", top: 53, zIndex: 19, background: C.sidebarBg,
            padding: "8px 12px 16px", display: "flex", flexDirection: "column",
            boxShadow: C.shadowMd,
          }}>
            {navItems}
            <div style={{ height: 8 }} />
            {logoutBtn}
          </nav>
        )}
        <main style={{ padding: "18px 16px", width: "100%", minWidth: 0 }}>
          {pageContent}
        </main>
      </div>
    );
  }

  // Desktop: fixed sidebar + content.
  return (
    <div style={{ minHeight: "100vh", background: C.bg, display: "flex", font: `400 14px ${FONT_DISPLAY}` }}>
      <aside style={{
        width: 240, background: C.sidebarBg, padding: "22px 12px",
        flexShrink: 0, display: "flex", flexDirection: "column",
      }}>
        <div style={{ font: `800 18px ${FONT_DISPLAY}`, color: C.sidebarText, padding: "0 12px 22px" }}>
          AthFuelPath Admin
        </div>
        {navItems}
        <div style={{ flex: 1 }} />
        {logoutBtn}
      </aside>

      <main style={{ flex: 1, minWidth: 0, padding: "28px 32px", width: "100%" }}>
        {pageContent}
      </main>
    </div>
  );
}

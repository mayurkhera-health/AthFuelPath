import { useState, useEffect } from "react";
import {
  requestPermission, subscribePush, unsubscribePush,
  getPrefs, savePrefs, sendTestNotification,
} from "./notificationService";

const REMINDERS = [
  {
    key: "remind_pregame_meal",
    title: "Pre-Game Meal",
    description: "Reminder to eat a full meal 3 hours before a game or practice",
    icon: "🍝",
  },
  {
    key: "remind_pregame_snack",
    title: "Pre-Game Snack",
    description: "Quick snack reminder 1 hour before a game or tournament",
    icon: "🍌",
  },
  {
    key: "remind_hydration",
    title: "Hydration Check",
    description: "Drink water before, during, and after training days",
    icon: "💧",
  },
  {
    key: "remind_meal_log",
    title: "Daily Meal Log",
    description: "Evening reminder to log today's meals if not yet tracked",
    icon: "📋",
  },
];

export default function NotificationsScreen({ athlete }) {
  const [permission, setPermission]   = useState(Notification?.permission || "default");
  const [subscribed, setSubscribed]   = useState(false);
  const [prefs, setPrefs]             = useState({
    remind_pregame_meal:  true,
    remind_pregame_snack: true,
    remind_hydration:     true,
    remind_meal_log:      true,
  });
  const [loading, setLoading]         = useState(true);
  const [toggling, setToggling]       = useState(false);
  const [saving, setSaving]           = useState(false);
  const [testSent, setTestSent]       = useState(false);
  const [error, setError]             = useState("");

  useEffect(() => {
    getPrefs(athlete.id).then((p) => {
      if (p) { setSubscribed(p.subscribed); setPrefs(p); }
      setLoading(false);
    });
  }, [athlete.id]);

  async function handleEnable() {
    setToggling(true); setError("");
    try {
      const perm = await requestPermission();
      setPermission(perm);
      if (perm !== "granted") {
        setError("Permission denied. Please allow notifications in your browser settings.");
        return;
      }
      const ok = await subscribePush(athlete.id);
      if (ok) setSubscribed(true);
      else setError("Failed to subscribe. Your browser may not support push notifications.");
    } catch (e) {
      setError(e.message);
    } finally {
      setToggling(false);
    }
  }

  async function handleDisable() {
    setToggling(true);
    await unsubscribePush(athlete.id);
    setSubscribed(false);
    setToggling(false);
  }

  async function handlePrefToggle(key) {
    const updated = { ...prefs, [key]: !prefs[key] };
    setPrefs(updated);
    setSaving(true);
    await savePrefs(athlete.id, updated);
    setSaving(false);
  }

  async function handleTest() {
    setTestSent(false);
    await sendTestNotification(athlete.id);
    setTestSent(true);
    setTimeout(() => setTestSent(false), 4000);
  }

  const supported = "Notification" in window && "serviceWorker" in navigator && "PushManager" in window;

  if (loading) return <p style={s.center}>Loading notification settings…</p>;

  return (
    <div>
      <div style={s.headerRow}>
        <h2 style={s.title}>Notifications</h2>
        {saving && <span style={s.savingLabel}>Saving…</span>}
      </div>

      {!supported && (
        <div style={s.warningBox}>
          ⚠️ Your browser doesn't support push notifications. Try Chrome or Edge.
        </div>
      )}

      {error && <div style={s.errorBox}>{error}</div>}

      {/* Enable / disable toggle */}
      <div style={s.mainCard}>
        <div style={s.mainCardLeft}>
          <div style={s.mainCardTitle}>Push Notifications</div>
          <div style={s.mainCardDesc}>
            {subscribed
              ? "Notifications are active. AthFuelPath will remind you about meals, hydration, and meal logging."
              : "Enable browser push notifications to get meal timing reminders for " + athlete.first_name + "."}
          </div>
          {permission === "denied" && (
            <div style={s.deniedNote}>
              Notifications are blocked in your browser. Go to browser Settings → Site Settings → Notifications to allow AthFuelPath.
            </div>
          )}
        </div>
        <div>
          {subscribed
            ? <button style={s.disableBtn} onClick={handleDisable} disabled={toggling}>{toggling ? "…" : "Turn Off"}</button>
            : <button style={s.enableBtn}  onClick={handleEnable}  disabled={toggling || !supported}>{toggling ? "Enabling…" : "Enable"}</button>
          }
        </div>
      </div>

      {/* Per-reminder toggles */}
      <div style={s.section}>
        <div style={s.sectionTitle}>Reminder Types</div>
        <div style={s.sectionDesc}>All reminders are on by default. Toggle any off.</div>

        {REMINDERS.map((r) => (
          <div key={r.key} style={s.reminderRow}>
            <div style={s.reminderIcon}>{r.icon}</div>
            <div style={s.reminderBody}>
              <div style={s.reminderTitle}>{r.title}</div>
              <div style={s.reminderDesc}>{r.description}</div>
            </div>
            <label style={s.toggle}>
              <input
                type="checkbox"
                checked={prefs[r.key] ?? true}
                onChange={() => handlePrefToggle(r.key)}
                disabled={!subscribed}
                style={{ display: "none" }}
              />
              <div style={{
                ...s.toggleTrack,
                background: (prefs[r.key] && subscribed) ? "#2d6a4f" : "#c8d8d0",
              }}>
                <div style={{
                  ...s.toggleThumb,
                  transform: (prefs[r.key] && subscribed) ? "translateX(20px)" : "translateX(0)",
                }} />
              </div>
            </label>
          </div>
        ))}
      </div>

      {/* Test button */}
      {subscribed && (
        <div style={s.testCard}>
          <div style={s.testLeft}>
            <div style={s.testTitle}>Test Notifications</div>
            <div style={s.testDesc}>Send a test push notification now to confirm they're working.</div>
          </div>
          <button style={s.testBtn} onClick={handleTest}>
            {testSent ? "✅ Sent!" : "Send Test"}
          </button>
        </div>
      )}

      {/* How it works */}
      <div style={s.howCard}>
        <div style={s.howTitle}>How reminders work</div>
        {[
          { icon: "🍝", text: "Pre-game meal alert sent 3 hours before any game or practice" },
          { icon: "🍌", text: "Pre-game snack alert sent 1 hour before games and tournaments" },
          { icon: "💧", text: "Hydration reminder sent on all training days" },
          { icon: "📋", text: "Meal log reminder sent each evening if meals haven't been logged" },
        ].map((item, i) => (
          <div key={i} style={s.howRow}>
            <span style={s.howIcon}>{item.icon}</span>
            <span style={s.howText}>{item.text}</span>
          </div>
        ))}
      </div>

      <p style={s.disclaimer}>Reminders are based on your training schedule. Add events in the Schedule tab to activate game-day alerts.</p>
    </div>
  );
}

const s = {
  center: { textAlign: "center", color: "#8aa898", padding: "40px 0" },
  headerRow: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" },
  title: { fontSize: "23px", fontWeight: "700", color: "#1b3a2a", margin: 0 },
  savingLabel: { fontSize: "17px", color: "#8aa898" },
  warningBox: { background: "#fffbeb", border: "1.5px solid #fde68a", borderRadius: "10px", padding: "12px 16px", fontSize: "18px", color: "#92400e", marginBottom: "16px" },
  errorBox: { background: "#fef2f2", border: "1.5px solid #fecaca", borderRadius: "10px", padding: "12px 16px", fontSize: "18px", color: "#dc2626", marginBottom: "16px" },

  mainCard: { display: "flex", justifyContent: "space-between", alignItems: "center", background: "#f4f8f5", border: "1.5px solid #e5e7eb", borderRadius: "14px", padding: "20px", marginBottom: "16px", gap: "16px" },
  mainCardLeft: { flex: 1 },
  mainCardTitle: { fontSize: "21px", fontWeight: "700", color: "#1b3a2a", marginBottom: "4px" },
  mainCardDesc: { fontSize: "18px", color: "#8aa898", lineHeight: 1.5 },
  deniedNote: { fontSize: "17px", color: "#dc2626", marginTop: "8px", lineHeight: 1.5 },
  enableBtn: { background: "linear-gradient(135deg, #2d6a4f, #52b788)", color: "#fff", border: "none", borderRadius: "8px", padding: "10px 20px", fontSize: "19px", fontWeight: "700", cursor: "pointer", whiteSpace: "nowrap" },
  disableBtn: { background: "transparent", color: "#dc2626", border: "1.5px solid #fecaca", borderRadius: "8px", padding: "10px 20px", fontSize: "19px", fontWeight: "700", cursor: "pointer", whiteSpace: "nowrap" },

  section: { border: "1.5px solid #e5e7eb", borderRadius: "14px", padding: "18px 20px", marginBottom: "16px" },
  sectionTitle: { fontSize: "19px", fontWeight: "700", color: "#1b3a2a", marginBottom: "4px" },
  sectionDesc: { fontSize: "17px", color: "#8aa898", marginBottom: "16px" },

  reminderRow: { display: "flex", alignItems: "center", gap: "14px", paddingBottom: "14px", marginBottom: "14px", borderBottom: "1px solid #f3f4f6" },
  reminderIcon: { fontSize: "25px", flexShrink: 0 },
  reminderBody: { flex: 1 },
  reminderTitle: { fontSize: "19px", fontWeight: "600", color: "#1b3a2a", marginBottom: "2px" },
  reminderDesc: { fontSize: "17px", color: "#8aa898" },

  toggle: { cursor: "pointer", flexShrink: 0 },
  toggleTrack: { width: "44px", height: "24px", borderRadius: "99px", position: "relative", transition: "background 0.2s", cursor: "pointer" },
  toggleThumb: { position: "absolute", top: "3px", left: "3px", width: "18px", height: "18px", borderRadius: "50%", background: "#fff", boxShadow: "0 1px 3px rgba(0,0,0,0.2)", transition: "transform 0.2s" },

  testCard: { display: "flex", justifyContent: "space-between", alignItems: "center", background: "#f0fdf4", border: "1.5px solid #bbf7d0", borderRadius: "12px", padding: "16px 20px", marginBottom: "16px", gap: "16px" },
  testLeft: { flex: 1 },
  testTitle: { fontSize: "19px", fontWeight: "700", color: "#2d6a4f", marginBottom: "2px" },
  testDesc: { fontSize: "17px", color: "#8aa898" },
  testBtn: { background: "linear-gradient(135deg, #2d6a4f, #52b788)", color: "#fff", border: "none", borderRadius: "8px", padding: "8px 18px", fontSize: "18px", fontWeight: "700", cursor: "pointer", whiteSpace: "nowrap" },

  howCard: { background: "#f4f8f5", border: "1.5px solid #e5e7eb", borderRadius: "12px", padding: "16px 20px", marginBottom: "16px" },
  howTitle: { fontSize: "18px", fontWeight: "700", color: "#4a6358", marginBottom: "12px" },
  howRow: { display: "flex", gap: "10px", marginBottom: "8px", alignItems: "flex-start" },
  howIcon: { fontSize: "21px", flexShrink: 0 },
  howText: { fontSize: "18px", color: "#8aa898", lineHeight: 1.5 },

  disclaimer: { textAlign: "center", fontSize: "16px", color: "#8aa898", marginTop: "8px" },
};

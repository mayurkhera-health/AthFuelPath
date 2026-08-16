import { useState } from "react";
import AppShell from "./AppShell";

export default function Dashboard({ parent, athletes, initialTab = "nutrition", isNewAccount = false, onUnlockApp, onSignOut }) {
  const [selectedAthlete, setSelectedAthlete] = useState(
    athletes.length === 1 ? athletes[0] : null
  );

  if (selectedAthlete) {
    return (
      <AppShell
        athlete={selectedAthlete}
        parent={parent}
        initialTab={initialTab}
        isNewAccount={isNewAccount}
        onUnlockApp={onUnlockApp}
        onSignOut={onSignOut}
      />
    );
  }

  return (
    <div style={s.wrapper}>
      <div style={s.card}>
        <div style={s.header}>
          <div style={s.logo}>⚽ AthFuelPath</div>
          <div style={s.subtitle}>Youth Sports Performance Nutrition Platform</div>
        </div>
        <h2 style={s.title}>Welcome back, {parent.full_name.split(" ")[0]}!</h2>
        <p style={s.desc}>Select an athlete to continue.</p>
        {athletes.map(a => (
          <button key={a.id} style={s.athleteCard} onClick={() => setSelectedAthlete(a)}>
            <div style={s.athleteName}>{a.first_name}</div>
            <div style={s.athleteMeta}>Age {a.age} · {a.gender} · {a.position || "—"} · {a.competition_level || "—"}</div>
            <div style={s.arrow}>View Dashboard →</div>
          </button>
        ))}
        <button style={s.signOut} onClick={onSignOut}>Sign Out</button>
      </div>
    </div>
  );
}

const s = {
  wrapper: { minHeight: "100vh", background: "linear-gradient(135deg, #0f4c35 0%, #1a7a54 100%)", display: "flex", alignItems: "center", justifyContent: "center", padding: "20px", fontFamily: "'Inter', -apple-system, sans-serif" },
  card: { background: "#fff", borderRadius: "20px", padding: "40px", width: "100%", maxWidth: "520px", boxShadow: "0 24px 60px rgba(0,0,0,0.25)" },
  header: { textAlign: "center", marginBottom: "28px" },
  logo: { fontSize: "31px", fontWeight: "800", color: "#0f4c35" },
  subtitle: { fontSize: "19px", color: "#6b7280", marginTop: "4px" },
  title: { fontSize: "25px", fontWeight: "700", color: "#111827", marginBottom: "4px" },
  desc: { fontSize: "19px", color: "#6b7280", marginBottom: "20px" },
  athleteCard: { width: "100%", background: "#f0fdf4", border: "1.5px solid #bbf7d0", borderRadius: "12px", padding: "16px 20px", marginBottom: "12px", textAlign: "left", cursor: "pointer" },
  athleteName: { fontSize: "23px", fontWeight: "700", color: "#0f4c35", marginBottom: "4px" },
  athleteMeta: { fontSize: "19px", color: "#374151", marginBottom: "8px" },
  arrow: { fontSize: "18px", fontWeight: "600", color: "#0f4c35" },
  signOut: { width: "100%", padding: "12px", background: "transparent", color: "#0f4c35", border: "2px solid #0f4c35", borderRadius: "10px", fontSize: "20px", fontWeight: "600", cursor: "pointer", marginTop: "8px" },
};

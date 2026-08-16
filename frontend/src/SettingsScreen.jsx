import { useState, useEffect } from "react";
import ProfileScreen from "./ProfileScreen";
import NotificationsScreen from "./NotificationsScreen";

const API = import.meta.env.VITE_API_URL ?? "";

const SECTIONS = [
  { id: "profile",       icon: "👤", label: "Athlete Profile",        desc: "Edit name, position, age, dietary needs, allergies" },
  { id: "notifications", icon: "🔔", label: "Notifications & Alerts",  desc: "Manage meal reminders and push notification settings" },
];

export default function SettingsScreen({ athlete, parent, onSave, onSignOut, onClose }) {
  const [section, setSection]                 = useState(null);
  const [legalDocs, setLegalDocs]             = useState([]);
  const [legalLoading, setLegalLoading]       = useState(true);
  const [legalError, setLegalError]           = useState(false);
  const [legalDocContent, setLegalDocContent] = useState(null);
  const [legalDocLoading, setLegalDocLoading] = useState(false);
  const [legalDocError, setLegalDocError]     = useState(false);
  const [retryKey, setRetryKey]               = useState(0);

  // Fetch document list on mount
  useEffect(() => {
    setLegalLoading(true);
    setLegalError(false);
    fetch(`${API}/api/legal/`)
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(data => { setLegalDocs(data); setLegalLoading(false); })
      .catch(() => { setLegalError(true); setLegalLoading(false); });
  }, []);

  // Fetch individual document whenever a legal section is selected or retried
  useEffect(() => {
    if (!section?.startsWith("legal:")) return;
    const slug = section.slice(6);
    setLegalDocContent(null);
    setLegalDocLoading(true);
    setLegalDocError(false);
    fetch(`${API}/api/legal/${slug}`)
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(data => { setLegalDocContent(data.content); setLegalDocLoading(false); })
      .catch(() => { setLegalDocError(true); setLegalDocLoading(false); });
  }, [section, retryKey]);

  if (section === "profile") {
    return (
      <div>
        <BackBar label="Athlete Profile" onBack={() => setSection(null)} />
        <ProfileScreen athlete={athlete} onSave={(updated) => { onSave(updated); setSection(null); }} />
      </div>
    );
  }

  if (section === "notifications") {
    return (
      <div>
        <BackBar label="Notifications & Alerts" onBack={() => setSection(null)} />
        <NotificationsScreen athlete={athlete} />
      </div>
    );
  }

  if (section?.startsWith("legal:")) {
    const slug  = section.slice(6);
    const title = legalDocs.find(d => d.slug === slug)?.title ?? "Legal Document";

    return (
      <div>
        <BackBar label={title} onBack={() => setSection(null)} />
        {legalDocLoading && !legalDocContent && <div style={s.legalPlaceholder}>Loading…</div>}
        {legalDocError && (
          <div>
            <div style={{ ...s.legalPlaceholder, color: "#dc2626" }}>Could not load document.</div>
            <button style={s.retryBtn} onClick={() => setRetryKey(k => k + 1)}>Retry</button>
          </div>
        )}
        {legalDocContent && (
          <div style={s.legalContent}>{legalDocContent}</div>
        )}
      </div>
    );
  }

  // Root settings menu
  return (
    <div>
      {/* Athlete identity card */}
      <div style={s.identityCard}>
        <div style={s.avatar}>
          {(athlete.first_name?.[0] || "?")}{(athlete.last_name?.[0] || "")}
        </div>
        <div>
          <div style={s.identityName}>{athlete.first_name} {athlete.last_name}</div>
          <div style={s.identityMeta}>
            Age {athlete.age} · {athlete.position || "Player"} · {athlete.level || ""}
          </div>
          <div style={s.identityParent}>Parent: {parent?.first_name} {parent?.last_name}</div>
        </div>
      </div>

      {/* Settings sections */}
      <div style={s.sectionLabel}>Account</div>
      {SECTIONS.map(sec => (
        <button key={sec.id} style={s.row} onClick={() => setSection(sec.id)}>
          <div style={s.rowIcon}>{sec.icon}</div>
          <div style={s.rowBody}>
            <div style={s.rowLabel}>{sec.label}</div>
            <div style={s.rowDesc}>{sec.desc}</div>
          </div>
          <div style={s.chevron}>›</div>
        </button>
      ))}

      {/* Legal section */}
      <div style={s.sectionLabel}>Legal</div>
      {legalLoading && (
        <div style={s.legalPlaceholder}>Loading…</div>
      )}
      {legalError && (
        <div style={{ ...s.legalPlaceholder, color: "#dc2626" }}>Could not load documents.</div>
      )}
      {!legalLoading && !legalError && legalDocs.map(doc => (
        <button key={doc.slug} style={s.row} onClick={() => setSection(`legal:${doc.slug}`)}>
          <div style={s.rowIcon}>⚖️</div>
          <div style={s.rowBody}>
            <div style={s.rowLabel}>{doc.title}</div>
          </div>
          <div style={s.chevron}>›</div>
        </button>
      ))}

      {/* About section */}
      <div style={s.sectionLabel}>About</div>
      <div style={s.infoRow}>
        <span style={s.infoLabel}>App</span>
        <span style={s.infoVal}>AthFuelPath v1.0</span>
      </div>
      <div style={s.infoRow}>
        <span style={s.infoLabel}>Powered by</span>
        <span style={s.infoVal}>Diets & Life RDN Team</span>
      </div>
      <div style={s.infoRow}>
        <span style={s.infoLabel}>Age range</span>
        <span style={s.infoVal}>9–17 years</span>
      </div>

      {/* Sign out */}
      <button style={s.signOutBtn} onClick={onSignOut}>Sign Out</button>

      <p style={s.disclaimer}>
        AthFuelPath provides educational food guidance — not medical nutrition therapy.<br />
        Always consult a registered dietitian for individualized advice.
      </p>
    </div>
  );
}

function BackBar({ label, onBack }) {
  return (
    <div style={bb.bar}>
      <button style={bb.btn} onClick={onBack}>‹ Back</button>
      <div style={bb.title}>{label}</div>
      <div style={{ width: "60px" }} />
    </div>
  );
}

const bb = {
  bar: { display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "20px", paddingBottom: "14px", borderBottom: "1.5px solid #e5e7eb" },
  btn: { background: "none", border: "none", color: "#2d6a4f", fontSize: "20px", fontWeight: "700", cursor: "pointer", padding: "4px 0" },
  title: { fontSize: "20px", fontWeight: "700", fontFamily: "'Nunito', sans-serif", color: "#1b3a2a" },
};

const s = {
  identityCard: { display: "flex", alignItems: "center", gap: "16px", background: "#f0fdf4", border: "1.5px solid #bbf7d0", borderRadius: "14px", padding: "18px 20px", marginBottom: "24px" },
  avatar: { width: "52px", height: "52px", borderRadius: "50%", background: "linear-gradient(135deg, #2d6a4f, #52b788)", color: "#fff", fontSize: "23px", fontWeight: "800", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, letterSpacing: "0.5px" },
  identityName: { fontSize: "21px", fontWeight: "800", fontFamily: "'Nunito', sans-serif", color: "#1b3a2a" },
  identityMeta: { fontSize: "18px", color: "#4a6358", marginTop: "2px" },
  identityParent: { fontSize: "17px", color: "#4a6358", marginTop: "2px" },

  sectionLabel: { fontSize: "16px", fontWeight: "700", color: "#4a6358", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "8px", marginTop: "8px" },

  row: { display: "flex", alignItems: "center", gap: "14px", width: "100%", background: "#fff", border: "1.5px solid #e5e7eb", borderRadius: "12px", padding: "14px 16px", marginBottom: "10px", cursor: "pointer", textAlign: "left" },
  rowIcon: { fontSize: "25px", flexShrink: 0 },
  rowBody: { flex: 1 },
  rowLabel: { fontSize: "19px", fontWeight: "700", fontFamily: "'Nunito', sans-serif", color: "#1b3a2a", marginBottom: "2px" },
  rowDesc: { fontSize: "17px", color: "#4a6358", lineHeight: 1.6 },
  chevron: { fontSize: "25px", color: "#4a6358", fontWeight: "400" },

  infoRow: { display: "flex", justifyContent: "space-between", padding: "10px 4px", borderBottom: "1px solid #f3f4f6" },
  infoLabel: { fontSize: "18px", color: "#4a6358" },
  infoVal: { fontSize: "18px", fontWeight: "600", color: "#4a6358" },

  signOutBtn: { width: "100%", marginTop: "24px", padding: "12px", background: "#fef2f2", color: "#dc2626", border: "1.5px solid #fecaca", borderRadius: "10px", fontSize: "19px", fontWeight: "700", cursor: "pointer" },

  disclaimer: { fontSize: "16px", color: "#8aa898", textAlign: "center", marginTop: "16px", lineHeight: 1.6 },
  legalPlaceholder: { padding: "10px 4px", fontSize: "17px", color: "#8aa898" },
  legalContent: {
    fontSize: "17px",
    lineHeight: 1.75,
    color: "#1b3a2a",
    whiteSpace: "pre-wrap",
    fontFamily: "'Nunito', sans-serif",
    padding: "0 4px 24px",
  },
  retryBtn: {
    marginTop: "8px",
    background: "none",
    border: "1px solid #2d6a4f",
    color: "#2d6a4f",
    borderRadius: "8px",
    padding: "6px 14px",
    fontSize: "17px",
    fontWeight: "700",
    cursor: "pointer",
    fontFamily: "'Nunito', sans-serif",
  },
};

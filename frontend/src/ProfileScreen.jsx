import { useState } from "react";

const API = import.meta.env.VITE_API_URL ?? "";

const POSITIONS   = ["Goalkeeper", "Defender", "Midfielder", "Forward"];
const LEVELS      = ["Recreational", "Competitive Club", "Elite Club"];
const GENDERS     = ["Girl", "Boy", "Prefer not to say"];
const ALLERGIES   = ["Gluten", "Dairy", "Eggs", "Peanuts", "Tree Nuts", "Fish", "Shellfish", "Soy", "Sesame"];
const DIETS       = ["Vegetarian", "Vegan", "Halal", "Kosher", "Gluten-Free", "Dairy-Free"];

function toggleItem(list, item) {
  const arr = list ? list.split(",").map(s => s.trim()).filter(Boolean) : [];
  return arr.includes(item) ? arr.filter(x => x !== item).join(", ") : [...arr, item].join(", ");
}

function hasItem(list, item) {
  return list ? list.split(",").map(s => s.trim().toLowerCase()).includes(item.toLowerCase()) : false;
}

export default function ProfileScreen({ athlete, onSave }) {
  const [form, setForm] = useState({
    first_name:           athlete.first_name       || "",
    age:                  athlete.age              || "",
    gender:               athlete.gender           || "",
    weight_lbs:           athlete.weight_lbs       || "",
    height_ft:            athlete.height_ft        || "",
    height_in:            athlete.height_in        || "",
    position:             athlete.position         || "",
    competition_level:    athlete.competition_level|| "",
    allergies:            athlete.allergies        || "",
    dietary_restrictions: athlete.dietary_restrictions || "",
  });

  const [saving, setSaving]   = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError]     = useState("");

  function set(key, val) {
    setForm(f => ({ ...f, [key]: val }));
    setSuccess(false);
  }

  async function handleSave(e) {
    e.preventDefault();
    if (!form.first_name.trim()) return setError("First name is required.");
    if (!form.age || form.age < 9 || form.age > 17) return setError("Age must be between 9 and 17.");
    if (!form.weight_lbs || !form.height_ft) return setError("Height and weight are required.");
    setSaving(true); setError(""); setSuccess(false);
    try {
      const res = await fetch(`${API}/api/athletes/${athlete.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...form,
          parent_id:    athlete.parent_id,
          age:          parseInt(form.age),
          weight_lbs:   parseFloat(form.weight_lbs),
          height_ft:    parseInt(form.height_ft),
          height_in:    parseFloat(form.height_in) || 0,
        }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || "Failed to save.");
      }
      const updated = await res.json();
      setSuccess(true);
      if (onSave) onSave(updated);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSave}>
      <div style={s.headerRow}>
        <h2 style={s.title}>Athlete Profile</h2>
        <button style={s.saveBtn} type="submit" disabled={saving}>
          {saving ? "Saving…" : "Save Changes"}
        </button>
      </div>

      {success && <div style={s.success}>✅ Profile updated successfully!</div>}
      {error   && <div style={s.error}>{error}</div>}

      {/* Basic info */}
      <div style={s.section}>
        <div style={s.sectionTitle}>Basic Info</div>
        <div style={s.row2}>
          <Field label="First Name">
            <input style={s.input} value={form.first_name} onChange={e => set("first_name", e.target.value)} placeholder="First name" />
          </Field>
          <Field label="Age">
            <input style={s.input} type="number" min="9" max="17" value={form.age} onChange={e => set("age", e.target.value)} placeholder="9–17" />
          </Field>
        </div>
        <div style={s.row2}>
          <Field label="Gender">
            <div style={s.chipRow}>
              {GENDERS.map(g => (
                <Chip key={g} label={g} active={form.gender === g} onClick={() => set("gender", g)} />
              ))}
            </div>
          </Field>
        </div>
      </div>

      {/* Physical stats */}
      <div style={s.section}>
        <div style={s.sectionTitle}>Physical Stats</div>
        <div style={s.row3}>
          <Field label="Weight (lbs)">
            <input style={s.input} type="number" step="0.1" value={form.weight_lbs} onChange={e => set("weight_lbs", e.target.value)} placeholder="e.g. 130" />
          </Field>
          <Field label="Height (ft)">
            <input style={s.input} type="number" value={form.height_ft} onChange={e => set("height_ft", e.target.value)} placeholder="e.g. 5" />
          </Field>
          <Field label="Height (in)">
            <input style={s.input} type="number" step="0.5" value={form.height_in} onChange={e => set("height_in", e.target.value)} placeholder="e.g. 6" />
          </Field>
        </div>
      </div>

      {/* Soccer profile */}
      <div style={s.section}>
        <div style={s.sectionTitle}>Soccer Profile</div>
        <Field label="Position">
          <div style={s.chipRow}>
            {POSITIONS.map(p => (
              <Chip key={p} label={p} active={form.position === p} onClick={() => set("position", p)} />
            ))}
          </div>
        </Field>
        <Field label="Competition Level" style={{ marginTop: "14px" }}>
          <div style={s.chipRow}>
            {LEVELS.map(l => (
              <Chip key={l} label={l} active={form.competition_level === l} onClick={() => set("competition_level", l)} />
            ))}
          </div>
          <p style={{ fontSize: "12px", color: "#6b7280", margin: "6px 0 0" }}>
            Recreational (AYSO, YMCA) · Competitive Club (travel clubs, NorCal, NPL lower) · Elite Club (ECNL, GA, MLS Next, DPL, EA)
          </p>
        </Field>
      </div>

      {/* Dietary */}
      <div style={s.section}>
        <div style={s.sectionTitle}>Dietary Needs</div>
        <Field label="Allergies">
          <div style={s.chipRow}>
            {ALLERGIES.map(a => (
              <Chip key={a} label={a} active={hasItem(form.allergies, a)} onClick={() => set("allergies", toggleItem(form.allergies, a))} />
            ))}
          </div>
          {form.allergies && <div style={s.selected}>Selected: {form.allergies}</div>}
        </Field>
        <Field label="Dietary Restrictions" style={{ marginTop: "14px" }}>
          <div style={s.chipRow}>
            {DIETS.map(d => (
              <Chip key={d} label={d} active={hasItem(form.dietary_restrictions, d)} onClick={() => set("dietary_restrictions", toggleItem(form.dietary_restrictions, d))} />
            ))}
          </div>
          {form.dietary_restrictions && <div style={s.selected}>Selected: {form.dietary_restrictions}</div>}
        </Field>
      </div>

      {/* Save footer */}
      <button style={s.saveBtnFull} type="submit" disabled={saving}>
        {saving ? "Saving…" : "Save Changes"}
      </button>
      <p style={s.disclaimer}>AthFuelPath provides educational food guidance — not medical nutrition therapy.</p>
    </form>
  );
}

function Field({ label, children, style }) {
  return (
    <div style={{ marginBottom: "4px", ...style }}>
      <label style={f.label}>{label}</label>
      {children}
    </div>
  );
}
const f = {
  label: { display: "block", fontSize: "17px", fontWeight: "600", color: "#8aa898", marginBottom: "6px" },
};

function Chip({ label, active, onClick }) {
  return (
    <button type="button" style={{ ...ch.base, ...(active ? ch.active : {}) }} onClick={onClick}>
      {label}
    </button>
  );
}
const ch = {
  base: { padding: "6px 12px", border: "1.5px solid #d1d5db", borderRadius: "99px", background: "#fff", fontSize: "18px", fontWeight: "600", color: "#8aa898", cursor: "pointer", marginBottom: "4px" },
  active: { background: "#2d6a4f", borderColor: "#2d6a4f", color: "#fff" },
};

const s = {
  headerRow: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" },
  title: { fontSize: "23px", fontWeight: "700", fontFamily: "'Nunito', sans-serif", color: "#1b3a2a", margin: 0 },
  saveBtn: { background: "linear-gradient(135deg, #2d6a4f, #52b788)", color: "#fff", border: "none", borderRadius: "8px", padding: "8px 18px", fontSize: "18px", fontWeight: "700", cursor: "pointer" },
  saveBtnFull: { width: "100%", padding: "12px", background: "linear-gradient(135deg, #2d6a4f, #52b788)", color: "#fff", border: "none", borderRadius: "10px", fontSize: "20px", fontWeight: "700", cursor: "pointer", marginTop: "8px", marginBottom: "12px" },
  success: { background: "#f0fdf4", border: "1.5px solid #bbf7d0", borderRadius: "8px", padding: "10px 14px", fontSize: "18px", fontWeight: "600", color: "#2d6a4f", marginBottom: "16px" },
  error: { background: "#fef2f2", border: "1.5px solid #fecaca", borderRadius: "8px", padding: "10px 14px", fontSize: "18px", color: "#dc2626", marginBottom: "16px" },
  section: { background: "#f4f8f5", border: "1.5px solid #e5e7eb", borderRadius: "12px", padding: "18px 20px", marginBottom: "14px" },
  sectionTitle: { fontSize: "18px", fontWeight: "700", color: "#4a6358", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "14px" },
  row2: { display: "flex", gap: "12px", marginBottom: "12px" },
  row3: { display: "flex", gap: "12px" },
  input: { width: "100%", padding: "9px 12px", border: "1.5px solid #d1d5db", borderRadius: "8px", fontSize: "19px", boxSizing: "border-box", outline: "none", background: "#fff" },
  chipRow: { display: "flex", flexWrap: "wrap", gap: "6px" },
  hint: { fontSize: "16px", color: "#8aa898", marginTop: "6px" },
  selected: { fontSize: "17px", color: "#2d6a4f", marginTop: "6px", fontWeight: "600" },
  warning: { background: "#fffbeb", border: "1.5px solid #fde68a", borderRadius: "8px", padding: "10px 14px", fontSize: "17px", color: "#92400e", marginTop: "10px", lineHeight: 1.5 },
  disclaimer: { textAlign: "center", fontSize: "16px", color: "#8aa898" },
};

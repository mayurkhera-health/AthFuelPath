import { useState } from "react";

const API = import.meta.env.VITE_API_URL ?? "";

const CONSENT_TEXT = `I confirm my athlete is between 9 and 17 years of age.

I understand AthFuelPath is an educational food guidance tool — NOT medical nutrition therapy.

All recommendations are based on published pediatric sports nutrition research, including Everett MD 2025, AAP guidelines, and Boston Children's Hospital RDN recommendations.

AthFuelPath collects the athlete's name, age, gender, height, weight, food allergies, dietary restrictions, and game schedule for the sole purpose of generating personalized nutrition guidance.

This data is never sold or shared with third parties. It is used only to deliver AthFuelPath's nutrition guidance service.

I can request complete data deletion at any time by emailing purvi@dietsandlife.com.

I will consult my child's physician or a licensed Registered Dietitian Nutritionist for any medical nutrition concerns.`;


const STEPS = ["Age Check", "Parent Consent", "Athlete Profile", "Review", "All Set!"];


function ReviewCard({ athlete }) {
  const heightStr = athlete.height_ft && athlete.height_in !== ""
    ? `${athlete.height_ft}' ${athlete.height_in}"`
    : athlete.height_ft ? `${athlete.height_ft}'` : "—";
  const allergies = (() => {
    if (!Array.isArray(athlete.allergies)) return athlete.allergies || "None";
    const base = athlete.allergies.filter(a => a !== "Other");
    const custom = athlete.allergies.includes("Other") && athlete.other_allergy?.trim()
      ? [athlete.other_allergy.trim()]
      : [];
    const all = [...base, ...custom];
    return all.length ? all.join(", ") : "None";
  })();
  const rows = [
    ["Full Name", athlete.first_name || "—"],
    ["Age", athlete.age || "—"],
    ["Gender", athlete.gender || "—"],
    ["Weight", athlete.weight_lbs ? `${athlete.weight_lbs} lbs` : "—"],
    ["Height", heightStr],
    ["Position", athlete.position || "—"],
    ["Competition Level", athlete.competition_level || "—"],
    ["Food Allergies", allergies],
    ["Dietary Restrictions", athlete.dietary_restrictions || "None"],
  ];

  return (
    <div style={rv.card}>
      {rows.map(([label, val]) => (
        <div key={label} style={rv.row}>
          <span style={rv.label}>{label}</span>
          <span style={rv.val}>{val}</span>
        </div>
      ))}
    </div>
  );
}

const rv = {
  card: { background: "#f4f8f5", border: "1.5px solid #e5e7eb", borderRadius: "12px", overflow: "hidden" },
  row: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", padding: "10px 16px", borderBottom: "1px solid #f3f4f6", fontSize: "19px" },
  label: { color: "#4a6358", fontWeight: "600", flexShrink: 0, marginRight: "12px" },
  val: { color: "#1b3a2a", fontWeight: "500", textAlign: "right" },
  warn: { background: "#fffbeb", borderTop: "1.5px solid #fde68a", padding: "12px 16px", fontSize: "18px", color: "#92400e", lineHeight: "1.5" },
};

const initialParent = { full_name: "", email: "", consent_confirmed: false };
const initialAthlete = {
  first_name: "", age: "", gender: "", weight_lbs: "",
  height_ft: "", height_in: "", position: "", competition_level: "",
  sweat_profile: "", allergies: [], other_allergy: "", dietary_restrictions: "",
};

export default function Onboarding({ onComplete }) {
  const [step, setStep] = useState(0);
  const [athleteAge, setAthleteAge] = useState("");
  const [ageError, setAgeError] = useState("");
  const [parent, setParent] = useState(initialParent);
  const [athlete, setAthlete] = useState(initialAthlete);
  const [parentId, setParentId] = useState(null);
  const [athleteId, setAthleteId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // ── Step 0: Age Gate ────────────────────────────────────────────────────────
  function handleAgeCheck() {
    const age = parseInt(athleteAge);
    if (!age) return setAgeError("Please enter the athlete's age.");
    if (age < 9) return setAgeError("AthFuelPath is designed for youth athletes ages 9–17. Please consult your child's physician for nutrition guidance.");
    if (age > 17) return setAgeError("AthFuelPath is designed for youth athletes ages 9–17. For athletes 18+, we recommend consulting a CSSD-credentialed sports dietitian.");
    setAgeError("");
    setAthlete((a) => ({ ...a, age }));
    setStep(1);
  }

  // ── Step 1: Parent Consent ──────────────────────────────────────────────────
  async function handleParentSubmit(e) {
    e.preventDefault();
    if (!parent.consent_confirmed) return setError("You must read and accept the consent agreement to continue.");
    setLoading(true);
    setError("");
    try {
      const isTest = parent.email?.trim().toLowerCase() === "test@gmail.com";
      if (isTest) {
        await fetch(`${API}/api/parents/test-reset?email=test@gmail.com`, { method: "DELETE" });
      }
      const res = await fetch(`${API}/api/parents/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parent),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to create account.");
      setParentId(data.id);
      setStep(2);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  // ── Step 2: Athlete Profile — just advance to review ───────────────────────
  function handleAthleteSubmit(e) {
    e.preventDefault();
    setError("");
    setStep(2.5);
  }

  // ── Step 2.5: Confirm & submit to API ──────────────────────────────────────
  async function handleConfirmSubmit() {
    setLoading(true);
    setError("");
    try {
      const payload = {
        ...athlete,
        parent_id: parentId,
        age: parseInt(athlete.age),
        weight_lbs: parseFloat(athlete.weight_lbs),
        height_ft: parseInt(athlete.height_ft),
        height_in: parseFloat(athlete.height_in),
        allergies: (() => {
          const base = athlete.allergies.filter(a => a !== "Other");
          const custom = athlete.allergies.includes("Other") && athlete.other_allergy.trim()
            ? [athlete.other_allergy.trim()]
            : [];
          const all = [...base, ...custom];
          return all.length ? all.join(", ") : "None";
        })(),
        supplement_use: "None",
      };
      const res = await fetch(`${API}/api/athletes/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to create athlete profile.");
      setAthleteId(data.id);
      // Go straight to Blueprint — skip the success screen
      if (onComplete) {
        onComplete({ parentId, athleteId: data.id });
      } else {
        setStep(3);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function toggleCheckbox(field, value) {
    setAthlete((a) => ({
      ...a,
      [field]: a[field].includes(value)
        ? a[field].filter((v) => v !== value)
        : [...a[field], value],
    }));
  }


  return (
    <div style={styles.wrapper}>
      <div style={styles.card}>
        {/* Header */}
        <div style={styles.header}>
          <div style={styles.logo}>⚽ AthFuelPath</div>
          <div style={styles.subtitle}>Youth Sports Performance Nutrition Platform</div>
        </div>

        {/* Progress bar */}
        <div style={styles.progressBar}>
          {STEPS.map((label, i) => {
            const displayStep = step === 2.5 ? 3 : step;
            const active = i <= displayStep;
            const done   = i < displayStep;
            return (
              <div key={i} style={styles.stepItem}>
                <div style={{ ...styles.stepDot, ...(active ? styles.stepDotActive : {}) }}>
                  {done ? "✓" : i + 1}
                </div>
                <div style={{ ...styles.stepLabel, ...(active ? styles.stepLabelActive : {}) }}>
                  {label}
                </div>
              </div>
            );
          })}
        </div>

        {error && <div style={styles.errorBanner}>{error}</div>}

        {/* ── Step 0: Age Gate ── */}
        {step === 0 && (
          <div style={styles.section}>
            <h2 style={styles.sectionTitle}>Welcome to AthFuelPath!</h2>
            <p style={styles.sectionDesc}>
              Before we begin, please confirm your athlete's age. AthFuelPath is built exclusively for youth athletes ages 9–17.
            </p>
            <label style={styles.label}>Athlete's Age</label>
            <input
              style={styles.input}
              type="number"
              min="1"
              max="25"
              placeholder="Enter athlete's age"
              value={athleteAge}
              onChange={(e) => setAthleteAge(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleAgeCheck()}
            />
            {ageError && <div style={styles.fieldError}>{ageError}</div>}
            <button style={styles.btn} onClick={handleAgeCheck}>
              Continue →
            </button>
            <p style={styles.disclaimer}>
              AthFuelPath provides educational food guidance — not medical nutrition therapy.
            </p>
          </div>
        )}

        {/* ── Step 1: Parent Consent ── */}
        {step === 1 && (
          <form onSubmit={handleParentSubmit} style={styles.section}>
            <h2 style={styles.sectionTitle}>Parent Account + Consent</h2>
            <label style={styles.label}>Parent Full Name <span style={styles.req}>*</span></label>
            <input
              style={styles.input}
              type="text"
              placeholder="Your full name (acts as digital signature)"
              value={parent.full_name}
              onChange={(e) => setParent({ ...parent, full_name: e.target.value })}
              required
            />

            <label style={styles.label}>Parent Email <span style={styles.req}>*</span></label>
            <input
              style={styles.input}
              type="email"
              placeholder="your@email.com"
              value={parent.email}
              onChange={(e) => setParent({ ...parent, email: e.target.value })}
              required
            />

            <label style={styles.label}>Parental Consent Agreement <span style={styles.req}>*</span></label>
            <div style={styles.consentBox}>
              {CONSENT_TEXT.split("\n\n").map((para, i) => (
                <p key={i} style={styles.consentPara}>{para}</p>
              ))}
            </div>

            <label style={styles.checkboxRow}>
              <input
                type="checkbox"
                checked={parent.consent_confirmed}
                onChange={(e) => setParent({ ...parent, consent_confirmed: e.target.checked })}
                style={styles.checkbox}
              />
              <span>I have read and agree to all of the above consent terms.</span>
            </label>

            <button style={styles.btn} type="submit" disabled={loading}>
              {loading ? "Creating Account…" : "Create Account →"}
            </button>
          </form>
        )}

        {/* ── Step 2: Athlete Profile ── */}
        {step === 2 && (
          <form onSubmit={handleAthleteSubmit} style={styles.section}>
            <h2 style={styles.sectionTitle}>Athlete Profile</h2>
            <p style={styles.sectionDesc}>
              We collect only what's scientifically necessary to calculate personalized pediatric nutrition targets.
            </p>

            <div style={styles.row}>
              <div style={styles.col}>
                <label style={styles.label}>Full Name <span style={styles.req}>*</span></label>
                <input style={styles.input} type="text" placeholder="Athlete's full name" value={athlete.first_name}
                  onChange={(e) => setAthlete({ ...athlete, first_name: e.target.value })} required />
              </div>
              <div style={styles.col}>
                <label style={styles.label}>Age <span style={styles.req}>*</span></label>
                <input style={styles.input} type="number" value={athlete.age} readOnly />
              </div>
            </div>

            <label style={styles.label}>Gender <span style={styles.req}>*</span></label>
            <select style={styles.select} value={athlete.gender}
              onChange={(e) => setAthlete({ ...athlete, gender: e.target.value })} required>
              <option value="">Select gender</option>
              <option value="Girl">Girl</option>
              <option value="Boy">Boy</option>
              <option value="Prefer not to say">Prefer not to say</option>
            </select>
            {athlete.gender === "Girl" && (
              <div style={styles.infoNote}>Iron target: 15mg/day — 52% of female adolescent athletes are iron deficient (Everett MD 2025)</div>
            )}

            <div style={styles.row}>
              <div style={styles.col}>
                <label style={styles.label}>Weight (lbs) <span style={styles.req}>*</span></label>
                <input style={styles.input} type="number" step="0.1" placeholder="e.g. 130" value={athlete.weight_lbs}
                  onChange={(e) => setAthlete({ ...athlete, weight_lbs: e.target.value })} required />
              </div>
              <div style={styles.col}>
                <label style={styles.label}>Height (ft) <span style={styles.req}>*</span></label>
                <input style={styles.input} type="number" placeholder="5" value={athlete.height_ft}
                  onChange={(e) => setAthlete({ ...athlete, height_ft: e.target.value })} required />
              </div>
              <div style={styles.col}>
                <label style={styles.label}>Height (in) <span style={styles.req}>*</span></label>
                <input style={styles.input} type="number" step="0.5" placeholder="4" value={athlete.height_in}
                  onChange={(e) => setAthlete({ ...athlete, height_in: e.target.value })} required />
              </div>
            </div>

            <div style={styles.row}>
              <div style={styles.col}>
                <label style={styles.label}>Soccer Position</label>
                <select style={styles.select} value={athlete.position}
                  onChange={(e) => setAthlete({ ...athlete, position: e.target.value })}>
                  <option value="">Select position</option>
                  <option>Goalkeeper</option>
                  <option>Defender</option>
                  <option>Midfielder</option>
                  <option>Forward</option>
                </select>
              </div>
              <div style={styles.col}>
                <label style={styles.label}>Competition Level</label>
                <select style={styles.select} value={athlete.competition_level}
                  onChange={(e) => setAthlete({ ...athlete, competition_level: e.target.value })}>
                  <option value="">Select level</option>
                  <option>Recreational</option>
                  <option>Competitive Club</option>
                  <option>Elite Club</option>
                </select>
                <p style={{ fontSize: "12px", color: "#6b7280", margin: "6px 0 0" }}>
                  Recreational (AYSO, YMCA) · Competitive Club (most travel clubs, NorCal, NPL lower) · Elite Club (ECNL, GA, MLS Next, DPL, EA)
                </p>
              </div>
            </div>

            <label style={styles.label}>Food Allergies (select all that apply)</label>
            <div style={styles.checkGroup}>
              {["None", "Peanuts", "Tree nuts", "Dairy", "Eggs", "Gluten", "Soy", "Shellfish", "Other"].map((a) => (
                <label key={a} style={styles.checkboxRow}>
                  <input type="checkbox" checked={athlete.allergies.includes(a)}
                    onChange={() => toggleCheckbox("allergies", a)} style={styles.checkbox} />
                  <span>{a}</span>
                </label>
              ))}
            </div>
            {athlete.allergies.includes("Other") && (
              <input
                style={{ ...styles.input, marginTop: "8px" }}
                type="text"
                placeholder="Please describe the allergy"
                value={athlete.other_allergy}
                onChange={e => setAthlete({ ...athlete, other_allergy: e.target.value })}
              />
            )}

            <label style={styles.label}>Dietary Restrictions</label>
            <select style={styles.select} value={athlete.dietary_restrictions}
              onChange={(e) => setAthlete({ ...athlete, dietary_restrictions: e.target.value })}>
              <option value="">Select restriction</option>
              <option>No restrictions</option>
              <option>Vegetarian</option>
              <option>Vegan</option>
              <option>Halal</option>
              <option>Gluten-free</option>
            </select>

            <button style={styles.btn} type="submit" disabled={loading}>
              Continue to Review →
            </button>
          </form>
        )}

        {/* ── Step 2.5: Review ── */}
        {step === 2.5 && (
          <div style={styles.section}>
            <h2 style={styles.sectionTitle}>Review Athlete Profile</h2>
            <p style={styles.sectionDesc}>
              Please confirm everything looks correct. You can always edit this later in Settings.
            </p>
            <ReviewCard athlete={athlete} />
            <div style={{ display: "flex", gap: "12px", marginTop: "4px" }}>
              <button
                style={{ ...styles.btn, background: "#fff", color: "#2d6a4f", border: "1.5px solid #0f4c35", flex: "0 0 auto" }}
                onClick={() => setStep(2)}
              >
                ← Edit
              </button>
              <button style={{ ...styles.btn, flex: 1 }} onClick={handleConfirmSubmit} disabled={loading}>
                {loading ? "Saving…" : "Submit Profile →"}
              </button>
            </div>
          </div>
        )}

        {/* ── Step 3: Success ── */}
        {step === 3 && (
          <div style={{ ...styles.section, textAlign: "center" }}>
            <div style={styles.successIcon}>🏆</div>
            <h2 style={styles.sectionTitle}>Welcome to AthFuelPath!</h2>
            <p style={styles.sectionDesc}>
              Your athlete's profile is set up. AthFuelPath will now generate science-backed, personalized nutrition targets based on their training schedule every single day.
            </p>
            <div style={styles.summaryBox}>
              <div style={styles.summaryRow}><span>Parent ID</span><strong>#{parentId}</strong></div>
              <div style={styles.summaryRow}><span>Athlete ID</span><strong>#{athleteId}</strong></div>
              <div style={styles.summaryRow}><span>Next step</span><strong>Add your schedule →</strong></div>
            </div>
            <p style={styles.scienceNote}>
              Targets calculated using Everett MD 2025 · Boston Children's Hospital RDN · AAP guidelines
            </p>
            {onComplete && (
              <button style={styles.btn} onClick={() => onComplete({ parentId, athleteId })}>
                Add Training Schedule →
              </button>
            )}
            <p style={styles.disclaimer}>
              AthFuelPath provides educational food guidance — not medical nutrition therapy. Consult your child's physician for medical concerns.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

const styles = {
  wrapper: { minHeight: "100vh", background: "linear-gradient(135deg, #0f4c35 0%, #1a7a54 100%)", display: "flex", alignItems: "center", justifyContent: "center", padding: "20px", fontFamily: "'Nunito, DM Sans, sans-serif" },
  card: { background: "#fff", borderRadius: "20px", padding: "40px", width: "100%", maxWidth: "600px", boxShadow: "0 24px 60px rgba(0,0,0,0.25)" },
  header: { textAlign: "center", marginBottom: "28px" },
  logo: { fontSize: "31px", fontWeight: "800", color: "#2d6a4f" },
  subtitle: { fontSize: "19px", color: "#4a6358", marginTop: "4px" },
  progressBar: { display: "flex", justifyContent: "space-between", marginBottom: "32px", position: "relative" },
  stepItem: { display: "flex", flexDirection: "column", alignItems: "center", flex: 1 },
  stepDot: { width: "32px", height: "32px", borderRadius: "50%", background: "#dce8e0", color: "#4a6358", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "18px", fontWeight: "700", marginBottom: "6px" },
  stepDotActive: { background: "linear-gradient(135deg, #2d6a4f, #52b788)", color: "#fff" },
  stepLabel: { fontSize: "16px", color: "#4a6358", textAlign: "center" },
  stepLabelActive: { color: "#2d6a4f", fontWeight: "600" },
  section: { display: "flex", flexDirection: "column", gap: "16px" },
  sectionTitle: { fontSize: "25px", fontWeight: "700", fontFamily: "'Nunito', sans-serif", color: "#1b3a2a", margin: 0 },
  sectionDesc: { fontSize: "19px", color: "#4a6358", lineHeight: "1.5", margin: 0 },
  label: { fontSize: "18px", fontWeight: "600", color: "#4a6358" },
  req: { color: "#ef4444" },
  input: { padding: "10px 14px", border: "1.5px solid #d1d5db", borderRadius: "8px", fontSize: "20px", outline: "none", width: "100%", boxSizing: "border-box" },
  select: { padding: "10px 14px", border: "1.5px solid #d1d5db", borderRadius: "8px", fontSize: "20px", background: "#fff", width: "100%", boxSizing: "border-box" },
  row: { display: "flex", gap: "12px" },
  col: { display: "flex", flexDirection: "column", flex: 1, gap: "6px" },
  consentBox: { background: "#f4f8f5", border: "1.5px solid #e5e7eb", borderRadius: "8px", padding: "16px", maxHeight: "200px", overflowY: "auto", fontSize: "18px", lineHeight: "1.6", color: "#4a6358" },
  consentPara: { margin: "0 0 10px 0" },
  checkboxRow: { display: "flex", alignItems: "flex-start", gap: "10px", fontSize: "19px", color: "#4a6358", cursor: "pointer" },
  checkbox: { marginTop: "2px", accentColor: "#2d6a4f", width: "16px", height: "16px", flexShrink: 0 },
  checkGroup: { display: "flex", flexDirection: "column", gap: "8px", padding: "12px", background: "#f4f8f5", borderRadius: "8px", border: "1.5px solid #e5e7eb" },
  btn: { background: "linear-gradient(135deg, #2d6a4f, #52b788)", color: "#fff", border: "none", borderRadius: "10px", padding: "14px 24px", fontSize: "21px", fontWeight: "700", cursor: "pointer", marginTop: "8px" },
  errorBanner: { background: "#fef2f2", border: "1.5px solid #fecaca", borderRadius: "8px", padding: "12px 16px", color: "#dc2626", fontSize: "19px", marginBottom: "8px" },
  fieldError: { color: "#dc2626", fontSize: "18px", marginTop: "-8px" },
  infoNote: { background: "#f0fdf4", border: "1.5px solid #bbf7d0", borderRadius: "8px", padding: "10px 14px", fontSize: "18px", color: "#1b5e42" },
  warningBox: { background: "#fffbeb", border: "1.5px solid #fde68a", borderRadius: "8px", padding: "14px 16px", fontSize: "18px", color: "#92400e", lineHeight: "1.5" },
  successIcon: { fontSize: "59px", marginBottom: "8px" },
  summaryBox: { background: "#f0fdf4", border: "1.5px solid #bbf7d0", borderRadius: "12px", padding: "20px", display: "flex", flexDirection: "column", gap: "10px" },
  summaryRow: { display: "flex", justifyContent: "space-between", fontSize: "19px", color: "#4a6358" },
  scienceNote: { fontSize: "17px", color: "#4a6358" },
  disclaimer: { fontSize: "17px", color: "#8aa898", textAlign: "center", lineHeight: "1.5" },
};

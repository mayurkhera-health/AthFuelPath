# Legal Settings Section Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Legal" section to the Settings drawer that lists five legal documents fetched from `/api/legal` and lets users read each one inline.

**Architecture:** All changes are confined to `frontend/src/SettingsScreen.jsx`. Two `useEffect` hooks handle fetching: one fetches the document list on mount from `GET /api/legal`; a second watches the `section` state and fetches `GET /api/legal/{slug}` whenever a legal document is selected. Navigation follows the existing section-swap pattern already used for Athlete Profile and Notifications.

**Tech Stack:** React (hooks), existing inline styles, `import.meta.env.VITE_API_URL` for the API base URL.

---

## File Map

| File | Change |
|------|--------|
| `frontend/src/SettingsScreen.jsx` | Add `const API`, all legal state, two `useEffect` hooks, Legal section rows, document detail view |

No new files. No backend changes.

---

### Task 1: Add API constant, state, and fetch effects

**Files:**
- Modify: `frontend/src/SettingsScreen.jsx` — top of file and inside `SettingsScreen` component

No existing test infrastructure in this project. Verification is manual (Task 4).

- [ ] **Step 1: Add `const API` after the imports**

Open `frontend/src/SettingsScreen.jsx`. After the three `import` lines and before the `const SECTIONS` line, add:

```jsx
const API = import.meta.env.VITE_API_URL ?? "";
```

- [ ] **Step 2: Add all legal state variables**

Inside `SettingsScreen`, replace the single existing state declaration line:

```jsx
const [section, setSection] = useState(null);
```

with:

```jsx
const [section, setSection]                 = useState(null);
const [legalDocs, setLegalDocs]             = useState([]);
const [legalLoading, setLegalLoading]       = useState(true);
const [legalError, setLegalError]           = useState(false);
const [legalDocContent, setLegalDocContent] = useState(null);
const [legalDocLoading, setLegalDocLoading] = useState(false);
const [legalDocError, setLegalDocError]     = useState(false);
const [retryKey, setRetryKey]               = useState(0);
```

- [ ] **Step 3: Add the two fetch effects**

Immediately after the state declarations (before any `if (section === …)` blocks), add:

```jsx
// Fetch document list on mount
useEffect(() => {
  setLegalLoading(true);
  setLegalError(false);
  fetch(`${API}/api/legal`)
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
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/SettingsScreen.jsx
git commit -m "feat(settings): add legal fetch state and effects"
```

---

### Task 2: Render the Legal section in the settings menu

**Files:**
- Modify: `frontend/src/SettingsScreen.jsx` — the root settings menu JSX and `s` styles object

- [ ] **Step 1: Add Legal section JSX between Account and About**

In the root settings menu `return (…)`, locate the `{/* About section */}` comment. Insert the following block immediately before it (after the closing `})}` of the Account `SECTIONS.map`):

```jsx
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
```

- [ ] **Step 2: Add `legalPlaceholder` to the `s` styles object**

At the end of the `const s = { … }` block, before the closing `};`, add:

```js
  legalPlaceholder: { padding: "10px 4px", fontSize: "14px", color: "#8aa898" },
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/SettingsScreen.jsx
git commit -m "feat(settings): render Legal section rows in settings menu"
```

---

### Task 3: Add document detail view

**Files:**
- Modify: `frontend/src/SettingsScreen.jsx` — add section handler block and new styles

- [ ] **Step 1: Add the document detail view handler**

After the `if (section === "notifications") { … }` block and before the root settings menu `return`, add:

```jsx
if (section?.startsWith("legal:")) {
  const slug  = section.slice(6);
  const title = legalDocs.find(d => d.slug === slug)?.title ?? "Legal Document";

  return (
    <div>
      <BackBar label={title} onBack={() => setSection(null)} />
      {legalDocLoading && <div style={s.legalPlaceholder}>Loading…</div>}
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
```

- [ ] **Step 2: Add `legalContent` and `retryBtn` to the `s` styles object**

Append to the `const s = { … }` block:

```js
  legalContent: {
    fontSize: "14px",
    lineHeight: 1.75,
    color: "#1b3a2a",
    whiteSpace: "pre-wrap",
    fontFamily: "'DM Sans', 'Nunito', sans-serif",
  },
  retryBtn: {
    marginTop: "8px",
    background: "none",
    border: "1px solid #2d6a4f",
    color: "#2d6a4f",
    borderRadius: "8px",
    padding: "6px 14px",
    fontSize: "14px",
    fontWeight: "700",
    cursor: "pointer",
  },
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/SettingsScreen.jsx
git commit -m "feat(settings): add Legal document detail view"
```

---

### Task 4: Manual verification

**Files:** none — read-only verification

- [ ] **Step 1: Start the dev servers**

In one terminal:
```bash
cd /Users/mayurkhera/AthFuelPath
source venv/bin/activate && python db/setup.py
uvicorn api.main:app --reload --port 8000
```

In a second terminal:
```bash
cd /Users/mayurkhera/AthFuelPath/frontend
npm run dev
```

- [ ] **Step 2: Verify document list loads**

Open the app in a browser. Log in, open Settings (top-right avatar). Confirm:
- A "Legal" section header appears between "Account" and "About"
- Five rows appear: Privacy Policy, Terms of Service, Medical Disclaimer, Youth Athlete Disclaimer, AI Recommendations Disclaimer
- Each row has a ⚖️ icon and a › chevron

- [ ] **Step 3: Verify document detail navigation**

Tap "Privacy Policy". Confirm:
- The view swaps to the detail view
- A "‹ Back" bar appears with the title "Privacy Policy"
- The full text of the privacy policy renders (prose with `#` headings visible as-is in pre-wrap)
- Tapping "‹ Back" returns to the Settings root with all five rows still visible
- Tapping a second document ("Terms of Service") fetches and shows its content

- [ ] **Step 4: Commit any fixes found during verification**

```bash
git add frontend/src/SettingsScreen.jsx
git commit -m "fix(settings): address issues found during Legal section verification"
```

Only run this step if fixes were needed. Skip if everything passed in Step 2–3.

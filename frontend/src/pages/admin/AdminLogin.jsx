import { useState } from "react";
import { adminLogin } from "./adminApi";
import { C, FONT_DISPLAY } from "./theme";
import { Button, TextInput } from "./ui";

export default function AdminLogin({ onAuth }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    if (!password || busy) return;
    setBusy(true);
    setError("");
    try {
      await adminLogin(password);
      onAuth();
    } catch (err) {
      setError(err.message || "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{
      minHeight: "100vh", background: C.bg, display: "flex",
      alignItems: "center", justifyContent: "center", padding: 20,
    }}>
      <form onSubmit={submit} style={{
        background: C.surface, border: `1px solid ${C.border}`, borderRadius: 16,
        boxShadow: C.shadowMd, padding: 32, width: 360, maxWidth: "100%",
      }}>
        <div style={{ font: `800 22px ${FONT_DISPLAY}`, color: C.text1 }}>AthFuelPath Admin</div>
        <div style={{ font: `400 14px ${FONT_DISPLAY}`, color: C.text3, marginTop: 4, marginBottom: 22 }}>
          Enter the admin password to continue.
        </div>
        <TextInput
          type="password" value={password} placeholder="Admin password"
          onChange={(e) => setPassword(e.target.value)}
        />
        {error && (
          <div style={{ font: `500 13px ${FONT_DISPLAY}`, color: C.danger, marginTop: 10 }}>{error}</div>
        )}
        <Button type="submit" disabled={busy || !password} style={{ width: "100%", marginTop: 18 }}>
          {busy ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    </div>
  );
}

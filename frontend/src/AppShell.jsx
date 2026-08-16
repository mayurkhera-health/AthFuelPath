import { useState, useRef, useEffect } from "react";
import HomeScreen from "./HomeScreen";
import Today from "./pages/Today";
import NutritionDashboard from "./NutritionDashboard";
import ScheduleScreen from "./ScheduleScreen";
import RecipesScreen from "./RecipesScreen";
import ReportsScreen from "./ReportsScreen";
import HydrationScreen from "./HydrationScreen";
import MealPlannerScreen from "./MealPlannerScreen";
import SettingsScreen from "./SettingsScreen";
import Blueprint from "./Blueprint";
import Library from "./pages/Library";

const TABS = [
  { id: "home",      label: "Today"       },
  { id: "nutrition", label: "Fuel Report"  },
  { id: "library",   label: "📚 Library"   },
  { id: "schedule",  label: "Schedule"    },
  { id: "meal-plan", label: "🍳 Meal Plan" },
  { id: "blueprint", label: "🏅 Blueprint" },
  { id: "hydration", label: "💧 Hydration" },
];

export default function AppShell({ athlete: initialAthlete, parent, initialTab = "home", isNewAccount = false, onUnlockApp, onSignOut }) {
  const [tab, setTab]           = useState(initialTab);
  const [athlete, setAthlete]   = useState(initialAthlete);
  const [showSettings, setShowSettings] = useState(false);
  const [newAccount, setNewAccount] = useState(isNewAccount);

  // Prevent the popstate handler from triggering another pushState
  const isPoppingRef = useRef(false);

  // Push a history entry whenever the active tab changes
  useEffect(() => {
    if (!isPoppingRef.current) {
      window.history.pushState({ appTab: tab }, "");
    }
    isPoppingRef.current = false;
  }, [tab]);

  // Handle browser/phone back button — return to previous tab
  useEffect(() => {
    function onPop(e) {
      const prevTab = e.state?.appTab;
      if (prevTab) {
        isPoppingRef.current = true;
        setShowSettings(false);
        setTab(prevTab);
      }
    }
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  function handleUnlockAndNavigate(tabId) {
    setNewAccount(false);
    onUnlockApp?.();
    setTab(tabId);
  }

  const [freshImport, setFreshImport] = useState(false);
  const tabBarRef = useRef(null);

  // Scroll tab bar so the active tab is always visible
  useEffect(() => {
    const bar = tabBarRef.current;
    if (!bar) return;
    const activeBtn = bar.querySelector("[data-active='true']");
    if (activeBtn) {
      const { offsetLeft, offsetWidth } = activeBtn;
      const { scrollLeft, clientWidth } = bar;
      if (offsetLeft < scrollLeft) {
        bar.scrollTo({ left: offsetLeft - 16, behavior: "smooth" });
      } else if (offsetLeft + offsetWidth > scrollLeft + clientWidth) {
        bar.scrollTo({ left: offsetLeft + offsetWidth - clientWidth + 16, behavior: "smooth" });
      }
    }
  }, [tab]);

  function handleScheduleImported() {
    setFreshImport(true);
    setTab("meal-plan");
  }

  // Blueprint only shows during first-run onboarding flow
  const visibleTabs = newAccount
    ? TABS.filter(t => t.id === "blueprint")
    : TABS.filter(t => t.id !== "blueprint");

  const initials = `${athlete.first_name?.[0] || ""}${athlete.last_name?.[0] || ""}`.toUpperCase();

  return (
    <div style={s.wrapper}>
      <div style={s.card}>

        {/* Top bar */}
        <div style={s.topBar}>
          <div>
            <div style={s.logo}>⚽ AthFuelPath</div>
            <div style={s.athleteLabel}>{athlete.first_name} {athlete.last_name}</div>
          </div>
          <button
            style={s.avatarBtn}
            onClick={() => setShowSettings(true)}
            title="Settings"
          >
            <div style={s.avatarCircle}>{initials}</div>
            <div style={s.gearBadge}>⚙</div>
          </button>
        </div>

        {/* Tab bar */}
        <div style={s.tabBar} ref={tabBarRef}>
          {visibleTabs.map(t => (
            <button
              key={t.id}
              data-active={tab === t.id}
              style={{ ...s.tab, ...(tab === t.id ? s.tabActive : {}) }}
              onClick={() => { setShowSettings(false); setTab(t.id); }}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Main content */}
        <div style={s.content}>
          {tab === "home"      && <Today               athlete={athlete} onNavigate={setTab} />}
          {tab === "meal-log"  && <HomeScreen          athlete={athlete} onNavigate={setTab} />}
          {tab === "nutrition" && <NutritionDashboard athlete={athlete} />}
          {tab === "library"   && <Library            athlete={athlete} />}
          {tab === "schedule"  && <ScheduleScreen     athlete={athlete} onScheduleImported={handleScheduleImported} />}
          {tab === "recipes"   && <RecipesScreen      athlete={athlete} />}
          {tab === "meal-plan" && <MealPlannerScreen   athlete={athlete} onNavigate={setTab} freshImport={freshImport} onFreshImportSeen={() => setFreshImport(false)} />}
          {tab === "blueprint" && <Blueprint           athlete={athlete} onAddSchedule={newAccount ? () => handleUnlockAndNavigate("schedule") : null} />}
          {tab === "reports"   && <ReportsScreen      athlete={athlete} />}
          {tab === "hydration" && <HydrationScreen    athlete={athlete} />}
        </div>

        {/* Settings overlay */}
        {showSettings && (
          <>
            {/* Backdrop */}
            <div style={s.backdrop} onClick={() => setShowSettings(false)} />

            {/* Drawer */}
            <div style={s.drawer}>
              <div style={s.drawerHeader}>
                <div style={s.drawerTitle}>Settings</div>
                <button style={s.drawerClose} onClick={() => setShowSettings(false)}>✕</button>
              </div>
              <div style={s.drawerBody}>
                <SettingsScreen
                  athlete={athlete}
                  parent={parent}
                  onSave={(updated) => { setAthlete(updated); }}
                  onSignOut={onSignOut}
                  onClose={() => setShowSettings(false)}
                />
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

const s = {
  wrapper: {
    minHeight: "100vh",
    background: "linear-gradient(155deg, #dce8e0 0%, #e8f2ec 50%, #f0f8f2 100%)",
    display: "flex",
    justifyContent: "center",
    padding: "20px",
    fontFamily: "'Nunito', 'DM Sans', sans-serif",
  },
  card: {
    background: "#fff",
    borderRadius: "20px",
    width: "100%",
    maxWidth: "700px",
    boxShadow: "0 20px 48px rgba(27,67,50,0.14)",
    height: "fit-content",
    overflow: "hidden",
    position: "relative",
  },

  topBar: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "18px 28px 12px",
    borderBottom: "1px solid #dce8e0",
  },
  logo: { fontSize: "25px", fontWeight: "900", color: "#2d6a4f", fontFamily: "'Nunito', sans-serif" },
  athleteLabel: { fontSize: "18px", color: "#8aa898", marginTop: "1px" },

  avatarBtn: {
    position: "relative",
    background: "none",
    border: "none",
    cursor: "pointer",
    padding: "0",
    display: "flex",
    alignItems: "center",
  },
  avatarCircle: {
    width: "40px",
    height: "40px",
    borderRadius: "50%",
    background: "linear-gradient(135deg, #2d6a4f, #52b788)",
    color: "#fff",
    fontSize: "19px",
    fontWeight: "800",
    fontFamily: "'Nunito', sans-serif",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    letterSpacing: "0.5px",
    boxShadow: "0 2px 8px rgba(45,106,79,0.28)",
  },
  gearBadge: {
    position: "absolute",
    bottom: "-2px",
    right: "-4px",
    background: "#fff",
    borderRadius: "50%",
    width: "16px",
    height: "16px",
    fontSize: "16px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    boxShadow: "0 1px 4px rgba(0,0,0,0.12)",
  },

  tabBar: {
    display: "flex",
    borderBottom: "1.5px solid #dce8e0",
    padding: "0 28px",
    overflowX: "auto",
    scrollbarWidth: "none",
    background: "#fff",
  },
  tab: {
    background: "none",
    border: "none",
    borderBottom: "2.5px solid transparent",
    padding: "12px 14px",
    fontSize: "18px",
    fontWeight: "700",
    fontFamily: "'Nunito', sans-serif",
    color: "#8aa898",
    cursor: "pointer",
    marginBottom: "-1.5px",
    whiteSpace: "nowrap",
    transition: "color 0.15s",
  },
  tabActive: { color: "#2d6a4f", borderBottomColor: "#2d6a4f" },

  content: { padding: "24px 28px 28px", background: "#f4f8f5" },

  // Settings overlay
  backdrop: {
    position: "absolute",
    inset: 0,
    background: "rgba(27,67,50,0.3)",
    zIndex: 10,
    borderRadius: "20px",
  },
  drawer: {
    position: "absolute",
    top: 0,
    right: 0,
    bottom: 0,
    width: "min(380px, 100%)",
    background: "#fff",
    zIndex: 11,
    borderRadius: "0 20px 20px 0",
    display: "flex",
    flexDirection: "column",
    boxShadow: "-8px 0 32px rgba(27,67,50,0.14)",
    animation: "slideIn 0.22s ease",
  },
  drawerHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "20px 24px 16px",
    borderBottom: "1.5px solid #dce8e0",
    flexShrink: 0,
  },
  drawerTitle: { fontSize: "22px", fontWeight: "800", color: "#1b3a2a", fontFamily: "'Nunito', sans-serif" },
  drawerClose: {
    background: "#f0f4f1",
    border: "none",
    borderRadius: "50%",
    width: "30px",
    height: "30px",
    fontSize: "19px",
    cursor: "pointer",
    color: "#8aa898",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontWeight: "700",
  },
  drawerBody: {
    flex: 1,
    overflowY: "auto",
    padding: "20px 24px 28px",
  },
};

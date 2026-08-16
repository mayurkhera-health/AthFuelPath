# Activity-Type Selector & Tagging (Mobile) Implementation Plan — Plan B

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let athletes tag each calendar event (synced or manually added) with one of the 7 activity types via a one-tap picker, persisting it to the backend `events.activity_type` column built in Plan A; nudge untagged events to be tagged.

**Architecture:** A pure helper module (`utils/activityType.ts`) holds the 7-option list, labels, and the PATCH request builder (unit-tested). A reusable `ActivityTypeSheet` modal presents the one-tap picker. The Add-Event form sets `activity_type` at create time; the Schedule list's `EventCard` shows the tagged type as a chip or, when untagged, a "Tap to set activity" nudge that opens the sheet and calls a new `useTagActivityType` mutation (`PATCH /api/events/:id/activity-type`).

**Tech Stack:** React Native / Expo SDK 54 (HARD-PINNED — use `./node_modules/.bin/expo`, never `npx expo`), TypeScript, @tanstack/react-query, jest + ts-jest + @testing-library/react-native. Repo root for all paths: `/Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile`.

---

## Scope note

This is **Plan B of two mobile plans.** It covers the **Activity-Type Selector & tagging** only. The **Today-tab rendering** of the new day-layout cards (visible event marker, keep_going oz/packets card, recharge/rebuild/everyday placement, evening wind-down) is **Plan C**, deferred because it requires (a) the backend `DAY_LAYOUT_V2` flag to be enabled, and (b) the backend "before-enabling" items from Plan A (thread client-local datetime for the 2-hour resolver; populate per-window open/close times + status in `cards_to_template_windows`). Tagging captured here is stored immediately and becomes user-visible once Plan C lands and the flag flips.

---

## Background facts (verified — read before starting)

**Backend API (Plan A, already deployed-ready behind code):**
- `POST /api/events/` accepts an optional `activity_type` (one of the 7 keys) — stored, defaults null.
- `PATCH /api/events/{id}/activity-type` body `{"activity_type": "<key>"}` → returns the updated event; rejects invalid keys with HTTP 422.
- The 7 valid keys: `practice`, `game`, `tournament`, `speed_sprint`, `strength_cond`, `active_recovery`, `double_session`.

**Mobile current state:**
- `hooks/useSchedule.ts` — `AthleteEvent` interface (no `activity_type` yet), `useAddEvent` (spreads `...data` into the POST body — so adding `activity_type` to the data flows through automatically), `useDeleteEvent`, ICS import hooks. ICS import (`utils/icsImport.ts` `parseAndPostIcs`) posts events with NO `activity_type` → they arrive untagged (null), which is the intended "synced event needs tagging" state.
- `constants/eventTypes.ts` — `EVENT_TYPES` (display config per `event_type`) and `EVENT_TYPE_OPTIONS` (4-option picker: practice/game/tournament/conditioning). `event_type` is the display/legacy field and is SEPARATE from the new `activity_type` (Plan A decision A).
- `app/(app)/schedule/add-event.tsx` — has a `PillPicker` component and `EVENT_TYPE_OPTIONS`; `eventType` state; builds the `addEvent.mutateAsync({...})` payload at line ~95.
- `app/(app)/schedule/index.tsx` — `EventCard({ item, onDelete })` at line ~376 renders each event (uses `EVENT_TYPES[item.event_type]`).
- `services/api.ts` — thin wrapper exposing `api.get/post/put/delete`. **Verify it exposes `api.patch`; if not, this plan adds it (Task 2 Step 0).**

**Test conventions:** Tests live in `__tests__/` (e.g. `__tests__/components/icsImport.test.ts` for pure logic, `__tests__/components/afpUi.render.test.tsx` for render tests). Run a single file with `npx jest <path>`. Typecheck with `npx tsc --noEmit 2>&1 | grep -v node_modules` (expect no output for touched files). Pure-logic TDD is the norm here; component wiring is verified by a render test + tsc.

**Design system:** Use `DS.*` tokens from `constants/colors.ts` (e.g. `DS.primary`, `DS.surfaceContainerLowest`, `DS.outlineVariant`, `DS.amber`). Older schedule screens use the `Colors.*` aliases — match the file you're editing. Card radius ≤ 12, pill radius 20–999. No new colors.

**Content rules (CLAUDE.md §14):** athlete-facing copy is positive; no banned words ("missed", "behind", etc.). The untagged nudge must read as an invitation ("Tap to set activity"), never a warning.

---

## File Structure

- **Create** `utils/activityType.ts` — pure: `ACTIVITY_TYPE_OPTIONS` (the 7), `activityTypeLabel(key)`, `isUntagged(event)`, `buildTagActivityTypeRequest(eventId, key)`. One responsibility: activity-type data + request shaping. Unit-tested.
- **Modify** `constants/eventTypes.ts` — re-export `ACTIVITY_TYPE_OPTIONS` location note (keep the 7-option source in `utils/activityType.ts` to avoid a colors.ts import cycle; eventTypes.ts stays display-only).
- **Modify** `hooks/useSchedule.ts` — add `activity_type?: string | null` to `AthleteEvent`; add `useTagActivityType()`.
- **Modify** `services/api.ts` — add `api.patch` if missing.
- **Create** `components/schedule/ActivityTypeSheet.tsx` — the one-tap 7-option modal picker.
- **Modify** `app/(app)/schedule/add-event.tsx` — activity_type state + inline picker + payload field.
- **Modify** `app/(app)/schedule/index.tsx` — `EventCard` shows tagged chip or untagged nudge → opens sheet → tags.
- **Create** `__tests__/components/activityType.test.ts` — unit tests for the pure helper.
- **Create** `__tests__/components/activityTypeSheet.render.test.tsx` — render test for the sheet.

---

## Task 1: Pure activity-type helper + the 7 options

**Files:**
- Create: `utils/activityType.ts`
- Test: `__tests__/components/activityType.test.ts`

- [ ] **Step 1: Write the failing test**

Create `__tests__/components/activityType.test.ts`:

```ts
import {
  ACTIVITY_TYPE_OPTIONS,
  ACTIVITY_TYPE_KEYS,
  activityTypeLabel,
  isUntagged,
  buildTagActivityTypeRequest,
} from "../../utils/activityType";

describe("activity type helper", () => {
  it("exposes exactly the 7 backend keys", () => {
    expect(ACTIVITY_TYPE_KEYS).toEqual([
      "practice", "game", "tournament", "speed_sprint",
      "strength_cond", "active_recovery", "double_session",
    ]);
  });

  it("every option has a key, label, and emoji", () => {
    expect(ACTIVITY_TYPE_OPTIONS).toHaveLength(7);
    for (const o of ACTIVITY_TYPE_OPTIONS) {
      expect(typeof o.key).toBe("string");
      expect(o.label.length).toBeGreaterThan(0);
      expect(o.emoji.length).toBeGreaterThan(0);
    }
  });

  it("activityTypeLabel returns the label for a key and a fallback for unknown", () => {
    expect(activityTypeLabel("game")).toBe("Game");
    expect(activityTypeLabel("speed_sprint")).toBe("Speed / Sprints");
    expect(activityTypeLabel(null)).toBe("Set activity");
    expect(activityTypeLabel("bogus")).toBe("Set activity");
  });

  it("isUntagged is true only when activity_type is null/undefined/invalid", () => {
    expect(isUntagged({ activity_type: null })).toBe(true);
    expect(isUntagged({ activity_type: undefined })).toBe(true);
    expect(isUntagged({ activity_type: "bogus" })).toBe(true);
    expect(isUntagged({ activity_type: "practice" })).toBe(false);
  });

  it("buildTagActivityTypeRequest shapes the PATCH url + body", () => {
    expect(buildTagActivityTypeRequest(42, "game")).toEqual({
      url: "/api/events/42/activity-type",
      body: { activity_type: "game" },
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile && npx jest __tests__/components/activityType.test.ts`
Expected: FAIL — cannot find module `../../utils/activityType`.

- [ ] **Step 3: Implement**

Create `utils/activityType.ts`:

```ts
// Activity-type data + request shaping for the one-tap selector (Plan B).
// The 7 keys MUST match the backend (activity_type_resolver.VALID_ACTIVITY_TYPES
// and activity_engine._PROFILES). event_type (display) is separate from this.

export interface ActivityTypeOption {
  key: string;
  label: string;
  emoji: string;
}

export const ACTIVITY_TYPE_OPTIONS: ActivityTypeOption[] = [
  { key: "practice",        label: "Practice / Training",     emoji: "⚽" },
  { key: "game",            label: "Game",                    emoji: "🏆" },
  { key: "tournament",      label: "Tournament",              emoji: "🥇" },
  { key: "speed_sprint",    label: "Speed / Sprints",         emoji: "⚡" },
  { key: "strength_cond",   label: "Strength & Conditioning", emoji: "🏋️" },
  { key: "active_recovery", label: "Active Recovery / Yoga",  emoji: "🧘" },
  { key: "double_session",  label: "Double Session",          emoji: "➕" },
];

export const ACTIVITY_TYPE_KEYS: string[] = ACTIVITY_TYPE_OPTIONS.map((o) => o.key);

const _LABEL_BY_KEY: Record<string, string> = Object.fromEntries(
  ACTIVITY_TYPE_OPTIONS.map((o) => [o.key, o.label]),
);

/** Display label for a stored activity_type, or "Set activity" when untagged/invalid. */
export function activityTypeLabel(key: string | null | undefined): string {
  if (key && _LABEL_BY_KEY[key]) return _LABEL_BY_KEY[key];
  return "Set activity";
}

/** True when an event has no valid activity_type tag yet (needs the one-tap picker). */
export function isUntagged(event: { activity_type?: string | null }): boolean {
  const at = event.activity_type;
  return !at || !ACTIVITY_TYPE_KEYS.includes(at);
}

/** Shape the PATCH request for tagging an event's activity_type. */
export function buildTagActivityTypeRequest(eventId: number, key: string): {
  url: string;
  body: { activity_type: string };
} {
  return { url: `/api/events/${eventId}/activity-type`, body: { activity_type: key } };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile && npx jest __tests__/components/activityType.test.ts`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile
git add utils/activityType.ts __tests__/components/activityType.test.ts
git commit -m "feat(mobile): activityType helper — 7 options, labels, PATCH request builder"
```

---

## Task 2: `api.patch` + `useTagActivityType` hook + AthleteEvent field

**Files:**
- Modify: `services/api.ts` (only if `patch` is missing)
- Modify: `hooks/useSchedule.ts`
- Test: `__tests__/components/activityType.test.ts` (append a hook-payload test)

- [ ] **Step 0: Ensure `api.patch` exists**

Read `services/api.ts`. If it exposes `get/post/put/delete` but NOT `patch`, add a `patch` method mirroring `put` (same signature: `patch(path, body)` → `fetch(..., { method: "PATCH", headers JSON, body: JSON.stringify(body) })`). If `patch` already exists, skip this step and note it.

- [ ] **Step 1: Write the failing test**

Append to `__tests__/components/activityType.test.ts`:

```ts
import { AthleteEvent } from "../../hooks/useSchedule";

describe("AthleteEvent activity_type field", () => {
  it("AthleteEvent accepts an optional activity_type", () => {
    const ev: AthleteEvent = {
      id: 1, event_name: "Sat practice", event_type: "practice",
      event_date: "2026-06-27", activity_type: "speed_sprint",
    };
    expect(ev.activity_type).toBe("speed_sprint");
    const untagged: AthleteEvent = {
      id: 2, event_name: "Synced", event_type: "practice", event_date: "2026-06-27",
    };
    expect(untagged.activity_type).toBeUndefined();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile && npx jest __tests__/components/activityType.test.ts`
Expected: FAIL — TS error: `activity_type` does not exist on `AthleteEvent`.

- [ ] **Step 3: Implement**

In `hooks/useSchedule.ts`, add `activity_type?: string | null;` to the `AthleteEvent` interface (after the `intensity?: string;` line):

```ts
  intensity?: string;
  activity_type?: string | null;   // one of the 7 engine keys; null/absent = untagged
```

Add the new mutation hook (after `useDeleteEvent`):

```ts
import { buildTagActivityTypeRequest } from "../utils/activityType";

export function useTagActivityType() {
  const qc = useQueryClient();
  return useMutation<AthleteEvent, Error, { eventId: number; activityType: string }>({
    mutationFn: ({ eventId, activityType }) => {
      const { url, body } = buildTagActivityTypeRequest(eventId, activityType);
      return api.patch(url, body);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["schedule"] });
      qc.invalidateQueries({ queryKey: ["today-view"] });
      qc.invalidateQueries({ queryKey: ["daily-summary"] });
      qc.invalidateQueries({ queryKey: ["meal-plan"] });
    },
  });
}
```

(Add the `buildTagActivityTypeRequest` import to the existing import block at the top of `useSchedule.ts`. `useMutation`/`useQueryClient` are already imported.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile && npx jest __tests__/components/activityType.test.ts`
Expected: PASS (6 tests). Also run `npx tsc --noEmit 2>&1 | grep -v node_modules` — expect no errors referencing useSchedule.ts / api.ts.

- [ ] **Step 5: Commit**

```bash
cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile
git add services/api.ts hooks/useSchedule.ts __tests__/components/activityType.test.ts
git commit -m "feat(mobile): useTagActivityType hook + AthleteEvent.activity_type + api.patch"
```

---

## Task 3: `ActivityTypeSheet` one-tap picker modal

**Files:**
- Create: `components/schedule/ActivityTypeSheet.tsx`
- Test: `__tests__/components/activityTypeSheet.render.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `__tests__/components/activityTypeSheet.render.test.tsx`:

```tsx
import React from "react";
import { render, fireEvent } from "@testing-library/react-native";
import { ActivityTypeSheet } from "../../components/schedule/ActivityTypeSheet";

describe("ActivityTypeSheet", () => {
  it("renders all 7 options when visible and fires onSelect with the key", () => {
    const onSelect = jest.fn();
    const onClose = jest.fn();
    const { getByText } = render(
      <ActivityTypeSheet visible={true} selected={null} onSelect={onSelect} onClose={onClose} />,
    );
    // a representative subset of the 7 labels render
    getByText("Game");
    getByText("Speed / Sprints");
    getByText("Active Recovery / Yoga");
    fireEvent.press(getByText("Game"));
    expect(onSelect).toHaveBeenCalledWith("game");
  });

  it("renders nothing interactive when not visible", () => {
    const { queryByText } = render(
      <ActivityTypeSheet visible={false} selected={null} onSelect={() => {}} onClose={() => {}} />,
    );
    expect(queryByText("Game")).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile && npx jest __tests__/components/activityTypeSheet.render.test.tsx`
Expected: FAIL — cannot find module `ActivityTypeSheet`.

- [ ] **Step 3: Implement**

Create `components/schedule/ActivityTypeSheet.tsx`:

```tsx
import { View, Text, StyleSheet, Modal, TouchableOpacity, Pressable } from "react-native";
import { DS } from "../../constants/colors";
import { ACTIVITY_TYPE_OPTIONS } from "../../utils/activityType";

interface Props {
  visible: boolean;
  selected: string | null;
  onSelect: (key: string) => void;
  onClose: () => void;
}

export function ActivityTypeSheet({ visible, selected, onSelect, onClose }: Props) {
  if (!visible) return null;
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose}>
        <Pressable style={styles.sheet} onPress={() => {}}>
          <Text style={styles.title}>What kind of activity?</Text>
          <Text style={styles.subtitle}>Tap once to set how this session is fueled.</Text>
          <View style={styles.grid}>
            {ACTIVITY_TYPE_OPTIONS.map((opt) => {
              const isSel = selected === opt.key;
              return (
                <TouchableOpacity
                  key={opt.key}
                  style={[styles.chip, isSel && styles.chipSelected]}
                  onPress={() => onSelect(opt.key)}
                  accessibilityRole="button"
                  accessibilityLabel={opt.label}
                >
                  <Text style={styles.chipEmoji}>{opt.emoji}</Text>
                  <Text style={[styles.chipLabel, isSel && styles.chipLabelSelected]}>{opt.label}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.35)", justifyContent: "flex-end" },
  sheet: {
    backgroundColor: DS.surfaceContainerLowest,
    borderTopLeftRadius: 20, borderTopRightRadius: 20,
    padding: 20, paddingBottom: 32,
  },
  title: { fontSize: 18, fontWeight: "700", color: DS.onPrimaryContainer },
  subtitle: { fontSize: 13, color: DS.outline, marginTop: 4, marginBottom: 16 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  chip: {
    flexDirection: "row", alignItems: "center", gap: 8,
    paddingHorizontal: 14, paddingVertical: 12, borderRadius: 12,
    borderWidth: 1, borderColor: DS.outlineVariant, backgroundColor: DS.surfaceContainerLow,
  },
  chipSelected: { backgroundColor: DS.primary, borderColor: DS.primary },
  chipEmoji: { fontSize: 16 },
  chipLabel: { fontSize: 14, fontWeight: "600", color: DS.onPrimaryContainer },
  chipLabelSelected: { color: DS.onPrimary },
});
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile && npx jest __tests__/components/activityTypeSheet.render.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile
git add components/schedule/ActivityTypeSheet.tsx __tests__/components/activityTypeSheet.render.test.tsx
git commit -m "feat(mobile): ActivityTypeSheet — one-tap 7-option activity picker"
```

---

## Task 4: Set activity_type when adding an event

**Files:**
- Modify: `app/(app)/schedule/add-event.tsx`
- Test: manual (form screen — covered by tsc + the Task 1/2/3 unit/render tests)

- [ ] **Step 1: Add state + the picker + payload field**

In `app/(app)/schedule/add-event.tsx`:

1. Add the import:
```tsx
import { ActivityTypeSheet } from "../../../components/schedule/ActivityTypeSheet";
import { activityTypeLabel } from "../../../utils/activityType";
```

2. Add state near the other `useState` calls (after `eventType`):
```tsx
  const [activityType, setActivityType] = useState<string | null>(null);
  const [showActivitySheet, setShowActivitySheet] = useState(false);
```

3. Add `activity_type` to the `addEvent.mutateAsync({...})` payload (after `event_type: eventType,`):
```tsx
        event_type: eventType,
        ...(activityType ? { activity_type: activityType } : {}),
```

4. Add the picker trigger in the form JSX — place it right after the existing event-type `PillPicker` (the `<PillPicker options={EVENT_TYPE_OPTIONS} ... />` line). Insert:
```tsx
      <Text style={s.label}>Activity type (how it's fueled)</Text>
      <TouchableOpacity style={s.input} onPress={() => setShowActivitySheet(true)} activeOpacity={0.7}>
        <Text style={{ fontSize: 16, color: activityType ? Colors.textPrimary : Colors.textSecondary }}>
          {activityType ? activityTypeLabel(activityType) : "Tap to set (defaults to Practice)"}
        </Text>
      </TouchableOpacity>
      <ActivityTypeSheet
        visible={showActivitySheet}
        selected={activityType}
        onSelect={(k) => { setActivityType(k); setShowActivitySheet(false); }}
        onClose={() => setShowActivitySheet(false)}
      />
```
(Use the file's existing `s.label` / `s.input` styles — confirm those style keys exist in the screen's `StyleSheet`; if the label style key differs, match the nearby labels like the Event Name / Date labels. The `Colors` import already exists in this file.)

- [ ] **Step 2: Typecheck**

Run: `cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile && npx tsc --noEmit 2>&1 | grep -v node_modules`
Expected: no errors referencing `add-event.tsx`.

- [ ] **Step 3: Run the full mobile test suite to confirm nothing broke**

Run: `cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile && npx jest __tests__/components/activityType.test.ts __tests__/components/activityTypeSheet.render.test.tsx`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile
git add "app/(app)/schedule/add-event.tsx"
git commit -m "feat(mobile): set activity_type when adding an event"
```

---

## Task 5: Tag from the Schedule list (chip + untagged nudge)

**Files:**
- Modify: `app/(app)/schedule/index.tsx`
- Test: manual (screen) — logic covered by Task 1 (`isUntagged`, `activityTypeLabel`) unit tests + tsc

- [ ] **Step 1: Read `EventCard` and add the tagging affordance**

In `app/(app)/schedule/index.tsx`, read the `EventCard({ item, onDelete })` component (~line 376). Add the imports at the top of the file:
```tsx
import { useState } from "react";  // confirm useState is imported; the file already imports from react
import { ActivityTypeSheet } from "../../../components/schedule/ActivityTypeSheet";
import { useTagActivityType } from "../../../hooks/useSchedule";
import { activityTypeLabel, isUntagged } from "../../../utils/activityType";
```
(If `useState` is already imported at the top of this screen, don't duplicate it.)

Inside `EventCard`, add state + the mutation near the top of the component body:
```tsx
  const [showActivitySheet, setShowActivitySheet] = useState(false);
  const tagActivity = useTagActivityType();
  const untagged = isUntagged(item);
```

Add a tappable activity row inside the card's rendered content (place it after the existing event title/time row — match the card's existing layout; render it as the last line of the card body). Insert:
```tsx
      <TouchableOpacity
        style={card.activityRow}
        onPress={() => setShowActivitySheet(true)}
        activeOpacity={0.7}
        accessibilityRole="button"
        accessibilityLabel="Set activity type"
      >
        <Text style={[card.activityText, untagged && card.activityTextUntagged]}>
          {untagged ? "⚙ Tap to set activity" : `⚙ ${activityTypeLabel(item.activity_type)}`}
        </Text>
      </TouchableOpacity>
      <ActivityTypeSheet
        visible={showActivitySheet}
        selected={item.activity_type ?? null}
        onSelect={(k) => {
          setShowActivitySheet(false);
          tagActivity.mutate({ eventId: item.id, activityType: k });
        }}
        onClose={() => setShowActivitySheet(false)}
      />
```

Add the styles to the screen's existing `StyleSheet` block for `card` (or wherever `EventCard`'s styles live — match the existing style object name; below assumes a `card` StyleSheet — adapt the object name to the file's actual one):
```tsx
  activityRow: { marginTop: 8, paddingTop: 8, borderTopWidth: 1, borderTopColor: Colors.border },
  activityText: { fontSize: 13, fontWeight: "600", color: Colors.textPrimary },
  activityTextUntagged: { color: Colors.textSecondary, fontWeight: "500" },
```

- [ ] **Step 2: Typecheck**

Run: `cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile && npx tsc --noEmit 2>&1 | grep -v node_modules`
Expected: no errors referencing `schedule/index.tsx`.

- [ ] **Step 3: Commit**

```bash
cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile
git add "app/(app)/schedule/index.tsx"
git commit -m "feat(mobile): tag activity_type from Schedule list (chip + untagged nudge)"
```

---

## Task 6: Final verification (typecheck + full jest)

**Files:** none (verification only)

- [ ] **Step 1: Full typecheck**

Run: `cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile && npx tsc --noEmit 2>&1 | grep -v node_modules`
Expected: no NEW errors from this plan's files (`utils/activityType.ts`, `hooks/useSchedule.ts`, `services/api.ts`, `components/schedule/ActivityTypeSheet.tsx`, `app/(app)/schedule/add-event.tsx`, `app/(app)/schedule/index.tsx`). Pre-existing unrelated errors elsewhere are out of scope — report them but do not fix.

- [ ] **Step 2: Run this plan's tests**

Run: `cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile && npx jest __tests__/components/activityType.test.ts __tests__/components/activityTypeSheet.render.test.tsx`
Expected: all pass (8 tests total).

- [ ] **Step 3: Run the existing mobile suite to confirm no regression**

Run: `cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile && npx jest 2>&1 | tail -15`
Expected: the existing tests still pass; only the two new test files are added. Report any pre-existing failures (do not fix — they're out of scope).

- [ ] **Step 4: No commit** (verification only). If any step surfaced a real issue, fix it under the relevant task and re-run.

---

## After all tasks

- [ ] Use **superpowers:finishing-a-development-branch**.
- [ ] **Plan C (Today rendering) is next** — renders the tagged activity's day-layout on the Today tab. It requires enabling `DAY_LAYOUT_V2` and completing the Plan A "before-enabling" items (thread client-local datetime for the 2-hour resolver; populate per-window open/close + status in `cards_to_template_windows`). Until then, the tags captured here are stored but not yet reflected in the Today fuel windows.
- [ ] **Hand-off note for the user:** TestFlight build (`eas build --platform ios --profile preview`) is run by the user, never by the agent.

---

## Self-Review

**Spec coverage (Purvi "Activity Type Selector" section):**
- One-tap picker shown when an event is synced or added → Task 3 (sheet) + Task 4 (add) + Task 5 (Schedule list, incl. synced/untagged events) ✅
- The 7 activity types map to the engine keys → Task 1 (`ACTIVITY_TYPE_KEYS` matches backend) ✅
- "Defaults to Practice silently if not tagged within 2h" → backend-side (Plan A resolver); mobile shows the untagged nudge ("Tap to set") and the add-form hint "(defaults to Practice)" ✅ — the 2h auto-default itself is NOT mobile logic.
- Persists per event → Task 2 (`useTagActivityType` PATCH) + Task 4 (create payload) ✅

**Deferred (documented, not dropped):** the Today-tab rendering of the resulting day-layout is Plan C (needs `DAY_LAYOUT_V2` + Plan A before-enabling items). Flagged in the Scope note and After-all-tasks.

**Placeholder scan:** every code step has complete code; test steps have real assertions; the two screen-wiring tasks (4, 5) give exact snippets and instruct matching the file's existing style-object names (an explicit adaptation instruction, not a vague placeholder).

**Type consistency:** `activity_type?: string | null` used consistently (AthleteEvent, isUntagged, sheet `selected`/`onSelect(key:string)`). `useTagActivityType` variables `{ eventId, activityType }` consistent between Task 2 definition and Task 5 call site. `buildTagActivityTypeRequest(eventId, key)` signature consistent between Task 1 and Task 2. `ACTIVITY_TYPE_OPTIONS`/`ACTIVITY_TYPE_KEYS`/`activityTypeLabel`/`isUntagged` names consistent across Tasks 1, 3, 4, 5.

#!/usr/bin/env bash
#
# AthFuelPath dev-machine disk audit.
#
# READ-ONLY. This script deletes nothing. It measures the directories that
# actually grow on a Mac running this project (multiple worktrees, Python
# venvs, node_modules in two frontends, Xcode/Expo for the mobile app) and
# prints the reclaim command next to each finding so you decide what goes.
#
# Usage:  bash scripts/mac-disk-audit.sh
#         bash scripts/mac-disk-audit.sh --min 100    # only show >=100 MB
#
set -uo pipefail

MIN_MB=50
[ "${1:-}" = "--min" ] && MIN_MB="${2:-50}"

# ── helpers ──────────────────────────────────────────────────────────────────

# size_mb PATH -> integer MB (0 if missing). -x keeps du on one filesystem so
# network/external mounts don't turn a scan into a hang.
size_mb() {
  [ -e "$1" ] || { echo 0; return; }
  du -sxm "$1" 2>/dev/null | awk '{print $1+0}'
}

human() {
  awk -v m="$1" 'BEGIN{ if (m>=1024) printf "%.1f GB", m/1024; else printf "%d MB", m }'
}

TOTAL_FOUND=0

# report LABEL PATH RECLAIM_CMD
report() {
  local label="$1" path="$2" cmd="${3:-}" mb
  mb="$(size_mb "$path")"
  [ "$mb" -lt "$MIN_MB" ] && return
  TOTAL_FOUND=$((TOTAL_FOUND + mb))
  printf '  %-9s  %-52s  %s\n' "$(human "$mb")" "$label" "$path"
  [ -n "$cmd" ] && printf '             ↳ reclaim: %s\n' "$cmd"
}

section() { printf '\n\033[1m%s\033[0m\n' "$1"; }

# ── overall ──────────────────────────────────────────────────────────────────

section "DISK OVERVIEW"
df -h / /System/Volumes/Data 2>/dev/null | sed 's/^/  /'

section "PURGEABLE / SNAPSHOTS  (macOS may be holding space you can't see)"
# Time Machine local snapshots are the #1 cause of "disk full but nothing is big".
snaps="$(tmutil listlocalsnapshots / 2>/dev/null | grep -c 'com.apple' || true)"
case "$snaps" in (''|*[!0-9]*) snaps=0 ;; esac
printf '  %s local Time Machine snapshot(s)\n' "$snaps"
if [ "$snaps" -gt 0 ]; then
  printf '             ↳ reclaim: tmutil thinlocalsnapshots / 21474836480 4\n'
  printf '               (asks macOS to free ~20 GB of snapshots; safe, non-destructive to real files)\n'
fi

# ── this project ─────────────────────────────────────────────────────────────

section "ATHFUELPATH WORKTREES  (each clone carries its own venv + node_modules)"
found_wt=0
for d in "$HOME"/AthFuelPath*; do
  [ -d "$d" ] || continue
  found_wt=1
  mb="$(size_mb "$d")"
  printf '  %-9s  %s\n' "$(human "$mb")" "$d"
  report "  └─ Python venv"          "$d/venv"                    "rm -rf '$d/venv'   # rebuild: python3 -m venv venv && pip install -r requirements.txt"
  report "  └─ frontend/node_modules"       "$d/frontend/node_modules"       "rm -rf '$d/frontend/node_modules'   # rebuild: cd frontend && npm install"
  report "  └─ frontend-coach/node_modules" "$d/frontend-coach/node_modules" "rm -rf '$d/frontend-coach/node_modules'   # rebuild: cd frontend-coach && npm install"
  report "  └─ frontend/dist (build output)" "$d/frontend/dist"   "rm -rf '$d/frontend/dist'   # rebuild: cd frontend && npm run build"
  report "  └─ mobile node_modules"  "$d/mobile/node_modules"     "rm -rf '$d/mobile/node_modules'"
  report "  └─ Expo cache"           "$d/.expo"                   "rm -rf '$d/.expo'"
  report "  └─ iOS build"            "$d/ios/build"               "rm -rf '$d/ios/build'"
  report "  └─ Android build"        "$d/android/build"           "rm -rf '$d/android/build'"
  pyc_mb="$(find "$d" -type d -name __pycache__ -prune -exec du -sxm {} + 2>/dev/null | awk '{s+=$1} END{print s+0}')"
  if [ "${pyc_mb:-0}" -ge "$MIN_MB" ]; then
    printf '  %-9s  %s\n' "$(human "$pyc_mb")" "  └─ __pycache__ dirs (all)"
    printf '             ↳ reclaim: find '"'"'%s'"'"' -type d -name __pycache__ -prune -exec rm -rf {} +\n' "$d"
    TOTAL_FOUND=$((TOTAL_FOUND + pyc_mb))
  fi
done
[ "$found_wt" = 0 ] && printf '  (no ~/AthFuelPath* directories found)\n'

printf '\n  Stale worktrees registered in git:\n'
git -C "$HOME/AthFuelPath-main" worktree list 2>/dev/null | sed 's/^/    /' || printf '    (could not read ~/AthFuelPath-main)\n'
printf '             ↳ prune deleted ones: git -C ~/AthFuelPath-main worktree prune\n'

# ── developer caches: the usual heavyweights ─────────────────────────────────

section "XCODE / IOS  (routinely the largest single consumer on a Mac)"
report "DerivedData"            "$HOME/Library/Developer/Xcode/DerivedData"        "rm -rf ~/Library/Developer/Xcode/DerivedData/*   # safe, Xcode regenerates"
report "iOS DeviceSupport"      "$HOME/Library/Developer/Xcode/iOS DeviceSupport"  "rm -rf ~/Library/Developer/Xcode/'iOS DeviceSupport'/*   # safe; re-downloads per device"
report "watchOS DeviceSupport"  "$HOME/Library/Developer/Xcode/watchOS DeviceSupport" "rm -rf ~/Library/Developer/Xcode/'watchOS DeviceSupport'/*"
report "Xcode Archives"         "$HOME/Library/Developer/Xcode/Archives"           "REVIEW FIRST — these are shipped builds. Delete only old ones."
report "CoreSimulator Devices"  "$HOME/Library/Developer/CoreSimulator/Devices"    "xcrun simctl delete unavailable   # then review unused sims in Xcode"
report "CoreSimulator Caches"   "$HOME/Library/Developer/CoreSimulator/Caches"     "rm -rf ~/Library/Developer/CoreSimulator/Caches/*   # safe"

section "NODE / JS"
report "npm cache"              "$HOME/.npm"                  "npm cache clean --force   # safe"
report "yarn cache"             "$HOME/Library/Caches/Yarn"   "yarn cache clean   # safe"
report "pnpm store"             "$HOME/Library/pnpm/store"    "pnpm store prune   # safe"
report "Expo cache"             "$HOME/.expo"                 "rm -rf ~/.expo   # safe"
report "Metro/Haste cache"      "$HOME/Library/Caches/metro"  "rm -rf ~/Library/Caches/metro   # safe"

section "PYTHON"
report "pip cache"              "$HOME/Library/Caches/pip"    "pip cache purge   # safe"
report "pyenv versions"         "$HOME/.pyenv/versions"       "REVIEW FIRST — pyenv uninstall <version> for ones you no longer use"
report "uv cache"               "$HOME/.cache/uv"             "uv cache clean   # safe"

section "CONTAINERS / TOOLING"
report "Docker.raw disk image"  "$HOME/Library/Containers/com.docker.docker/Data/vms"  "docker system prune -a --volumes   # REVIEW: deletes unused images+volumes"
report "Docker (newer layout)"  "$HOME/Library/Containers/com.docker.docker/Data"      "docker system prune -a   # REVIEW"
report "Homebrew cache"         "$HOME/Library/Caches/Homebrew" "brew cleanup -s --prune=all   # safe"
report "Gradle caches"          "$HOME/.gradle/caches"         "rm -rf ~/.gradle/caches   # safe, re-downloads"
report "CocoaPods cache"        "$HOME/Library/Caches/CocoaPods" "pod cache clean --all   # safe"
report "Go module cache"        "$HOME/go/pkg/mod"             "go clean -modcache   # safe"
report "Rust target/registry"   "$HOME/.cargo/registry"        "rm -rf ~/.cargo/registry   # safe, re-downloads"

section "APP CACHES & SUPPORT  (safe to clear; apps rebuild them)"
report "Total ~/Library/Caches" "$HOME/Library/Caches"         "REVIEW: clear per-app subfolders rather than the whole tree"
report "Slack"                  "$HOME/Library/Application Support/Slack/Service Worker" "Slack → clear cache from within the app"
report "Chrome profile"         "$HOME/Library/Application Support/Google/Chrome"        "REVIEW: contains profiles/passwords. Clear cache via Chrome settings."
report "Xcode caches"           "$HOME/Library/Caches/com.apple.dt.Xcode"                "rm -rf ~/Library/Caches/com.apple.dt.Xcode   # safe"

section "THE USUAL SUSPECTS"
report "Downloads"              "$HOME/Downloads"              "REVIEW — sort by size in Finder, this is almost always reclaimable"
report "Desktop"                "$HOME/Desktop"                "REVIEW"
report "Trash"                  "$HOME/.Trash"                 "Empty Trash (space is NOT freed until you do)"
report "Mail downloads"         "$HOME/Library/Containers/com.apple.mail/Data/Library/Mail Downloads" "REVIEW — old attachments"
report "iOS device backups"     "$HOME/Library/Application Support/MobileSync/Backup"  "REVIEW — old iPhone backups, often 10s of GB"

# ── biggest files anywhere in home ───────────────────────────────────────────

section "20 LARGEST INDIVIDUAL FILES IN \$HOME  (may take a minute)"
find "$HOME" -xdev -type f -size +200M 2>/dev/null \
  | head -400 \
  | xargs -I{} du -xm "{}" 2>/dev/null \
  | sort -rn | head -20 \
  | awk '{ $1 = sprintf("%.1f GB", $1/1024); print "  " $0 }'

section "SUMMARY"
printf '  Reclaimable candidates identified (>= %s MB each): ~%s\n' "$MIN_MB" "$(human "$TOTAL_FOUND")"
printf '  Nothing was deleted. Run the reclaim commands above selectively.\n'
printf '  Re-run with --min 500 to see only the big wins.\n\n'

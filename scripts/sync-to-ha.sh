#!/usr/bin/env bash
# Sync custom_components/eink_esl straight onto a mounted HA /config share.
# No GitHub release needed — reload the integration (or restart Core) after.
#
# Usage:
#   ./scripts/sync-to-ha.sh /Volumes/config
#   ./scripts/sync-to-ha.sh /Volumes/config --restart   # needs SSH (see below)
#   HA_CONFIG=/Volumes/config ./scripts/sync-to-ha.sh
#
# Mount the Samba "config" share first (HA add-on: Samba share), e.g.:
#   open smb://homeassistant.local/config
# or: Finder → Go → Connect to Server → smb://192.168.100.74/config
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/custom_components/eink_esl"
DEST_ROOT="${1:-${HA_CONFIG:-}}"
DO_RESTART=0
if [[ "${2:-}" == "--restart" ]] || [[ "${1:-}" == "--restart" ]]; then
  DO_RESTART=1
  if [[ "${1:-}" == "--restart" ]]; then
    DEST_ROOT="${HA_CONFIG:-}"
  fi
fi

if [[ -z "$DEST_ROOT" ]]; then
  echo "Usage: $0 /path/to/ha/config [--restart]" >&2
  echo "Example: $0 /Volumes/config" >&2
  exit 2
fi

DEST="$DEST_ROOT/custom_components/eink_esl"
if [[ ! -d "$SRC" ]]; then
  echo "Missing source: $SRC" >&2
  exit 1
fi
if [[ ! -d "$DEST_ROOT" ]]; then
  echo "HA config path not mounted: $DEST_ROOT" >&2
  echo "Connect Samba: smb://homeassistant.local/config  (or your HA IP)" >&2
  exit 1
fi

mkdir -p "$DEST"
rsync -a --delete \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '.DS_Store' \
  "$SRC/" "$DEST/"

VER="$(python3 -c "import json; print(json.load(open('$SRC/manifest.json'))['version'])")"
echo "Synced eink_esl v$VER → $DEST"
echo "Next: Developer tools → YAML → Restart Home Assistant (or reload custom component)."

if [[ "$DO_RESTART" -eq 1 ]]; then
  if [[ -z "${HA_SSH:-}" ]]; then
    echo "--restart needs HA_SSH=user@host (Advanced SSH add-on), e.g.:" >&2
    echo "  HA_SSH=root@192.168.100.74 HA_SSH_PORT=22222 $0 $DEST_ROOT --restart" >&2
    exit 2
  fi
  ssh ${HA_SSH_PORT:+-p "$HA_SSH_PORT"} "$HA_SSH" "ha core restart"
  echo "Issued: ha core restart"
fi

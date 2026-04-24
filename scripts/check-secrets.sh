#!/usr/bin/env bash
set -euo pipefail

echo "Running refined secret scan..."

# Patterns for likely secrets (with length thresholds to avoid false positives)
PATTERN='sk-[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{35,}|ghp_[0-9A-Za-z_-]{36,}|gho_[0-9A-Za-z_-]{36,}|AKIA[0-9A-Z]{16,}|-----BEGIN PRIVATE KEY-----'

# Use git-tracked files when possible to limit scanning surface
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  FILES=$(git ls-files)
else
  FILES=$(find . -type f)
fi

TMPFILE=$(mktemp)
for f in $FILES; do
  # Skip common binary / sample files, internal folders and known whitelist files
  case "$f" in
    .git/*|backups/*|node_modules/*|.githooks/*|.github/*|.github/workflows/*|scripts/check-secrets.*|dashboards/*|*.png|*.jpg|*.jpeg|*.gif|*.svg|*.pdf|*.zip) continue ;;
    *.sample*|*.md|*.lock|*.html) continue ;;
  esac
  # grep with -I to skip binary files; label output with filename
  if grep -IEn --label "$f" -E "$PATTERN" "$f" >> "$TMPFILE" 2>/dev/null; then
    :
  fi
done

if [ -s "$TMPFILE" ]; then
  echo "POTENTIAL SECRETS FOUND:"
  sed -n '1,200p' "$TMPFILE"
  rm -f "$TMPFILE"
  echo
  echo "Review these files and move secrets into secure storage (.env.local is recommended and excluded)."
  exit 1
else
  echo "No obvious secrets found."
  rm -f "$TMPFILE"
  exit 0
fi

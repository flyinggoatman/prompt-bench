#!/usr/bin/env bash
#
# Build a Prompt Bench patch archive that install.sh understands.
#
#   tools/make-patch.sh [output.zip]
#
# The archive carries the shippable files at its top level, so install.sh
# unpacks them straight into the directory it sits in. Pass paths after the
# output name to ship a subset.
#
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
out="${1:-$repo/prompt-bench-patch.zip}"
shift || true

case "$out" in
  /*) ;;
  *)  out="$PWD/$out" ;;
esac

if [ "$#" -gt 0 ]; then
  items=("$@")
else
  items=(prompt-bench.html install.sh README.md DEPLOY.md server.py packs deploy legacy)
fi

present=()
for item in "${items[@]}"; do
  if [ -e "$repo/$item" ]; then present+=("$item"); else
    printf 'make-patch: skipping missing %s\n' "$item" >&2
  fi
done
[ "${#present[@]}" -gt 0 ] || { printf 'make-patch: nothing to package\n' >&2; exit 1; }

command -v zip >/dev/null 2>&1 || { printf 'make-patch: zip is not installed\n' >&2; exit 1; }
rm -f "$out"
( cd "$repo" && zip -qr "$out" "${present[@]}" \
    -x '*/.git/*' '*/.DS_Store' 'deploy/.env' 'uploads/*' )

printf 'make-patch: wrote %s\n' "$out"
printf 'make-patch: %s entries\n' "$(unzip -Z1 "$out" | wc -l | tr -d ' ')"

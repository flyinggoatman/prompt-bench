#!/usr/bin/env bash
#
# Prompt Bench patch installer.
#
# Put this script and the patch archive in the directory you want to update,
# then run the script. The patch is unpacked into that same directory:
#
#   /srv/prompt-bench/install.sh          <- this script
#   /srv/prompt-bench/prompt-bench-patch.zip
#   $ ./install.sh
#
# Wrapper directories inside the archive are discovered and skipped, so an
# archive shaped like Prompt-Bench/release/prompt-bench.html installs as
# prompt-bench.html beside this script, not as Prompt-Bench/release/...
#
# Files already in the destination that the patch does not mention are left
# alone. Files the patch supplies replace their counterparts. Deletions happen
# only when the patch carries a DELETE.txt manifest listing what to remove.
#
# Two things are never changed by an update:
#   - the owner and permissions of a folder that already exists. uploads/ is
#     owned by the container's user so the server can write to it, and copying
#     the patch's own uploads/ over it used to hand it back to root.
#   - live data the server writes: uploads/unlock-codes.db (the codes database
#     edited from the admin page). A patch's copy is installed only when there
#     is none yet.
#
# Usage:
#   ./install.sh [archive] [--dry-run] [--backup]
#
set -euo pipefail

# The whole script is one block that ends in exit. Bash reads and parses a
# block completely before running it, so when a patch replaces this very
# file partway through (most patches carry install.sh), the run carries on
# with the code it started with instead of reading the new file from the
# middle.
{

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
self="$(basename "${BASH_SOURCE[0]}")"
archive=""
dry_run=0
backup=0
tmp=""

die() { printf 'install: %s\n' "$*" >&2; exit 1; }
say() { printf 'install: %s\n' "$*"; }

cleanup() { [ -n "$tmp" ] && [ -d "$tmp" ] && rm -rf "$tmp"; }
trap cleanup EXIT INT TERM

for arg in "$@"; do
  case "$arg" in
    --dry-run) dry_run=1 ;;
    --backup)  backup=1 ;;
    -h|--help) sed -n '2,25p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*)        die "unknown option: $arg" ;;
    *)         archive="$arg" ;;
  esac
done

# ---- find the archive beside this script ------------------------------------
if [ -z "$archive" ]; then
  found=()
  while IFS= read -r -d '' f; do found+=("$f"); done < <(
    find "$here" -maxdepth 1 -type f \
      \( -name '*.zip' -o -name '*.tar.gz' -o -name '*.tgz' \) -print0 | sort -z
  )
  case "${#found[@]}" in
    0) die "no .zip or .tar.gz found beside $self. Pass one: ./$self patch.zip" ;;
    1) archive="${found[0]}" ;;
    *) printf 'install: several archives found, name the one to use:\n' >&2
       printf '  %s\n' "${found[@]##*/}" >&2; exit 1 ;;
  esac
fi
[ -f "$archive" ] || die "no such archive: $archive"
archive="$(cd "$(dirname "$archive")" && pwd)/$(basename "$archive")"
say "using $(basename "$archive")"

# ---- list the archive, and refuse anything that escapes it ------------------
case "$archive" in
  *.zip)            kind=zip ;;
  *.tar.gz|*.tgz)   kind=tar ;;
  *)                die "unsupported archive type: $archive" ;;
esac

if [ "$kind" = zip ]; then
  command -v unzip >/dev/null 2>&1 || die "unzip is needed to read $archive"
  listing="$(unzip -Z1 -- "$archive")" || die "could not read $archive"
else
  command -v tar >/dev/null 2>&1 || die "tar is needed to read $archive"
  listing="$(tar -tzf "$archive")" || die "could not read $archive"
fi
[ -n "$listing" ] || die "$archive is empty"

while IFS= read -r entry; do
  [ -n "$entry" ] || continue
  case "$entry" in
    /*|*/../*|../*|*/..) die "refusing $archive: entry escapes the archive: $entry" ;;
    ..) die "refusing $archive: entry escapes the archive: $entry" ;;
  esac
done <<< "$listing"

# ---- unpack to a staging directory, never to the destination ----------------
tmp="$(mktemp -d "${TMPDIR:-/tmp}/prompt-bench-patch.XXXXXX")" || die "could not make a temporary directory"
stage="$tmp/stage"
mkdir -p "$stage"

if [ "$kind" = zip ]; then
  unzip -qq -- "$archive" -d "$stage" || die "could not unpack $archive"
else
  tar -xzf "$archive" -C "$stage" || die "could not unpack $archive"
fi

# ---- descend wrapper directories to find the real package root --------------
root="$stage"
while :; do
  count="$(find "$root" -mindepth 1 -maxdepth 1 | wc -l | tr -d ' ')"
  [ "$count" = "1" ] || break
  only="$(find "$root" -mindepth 1 -maxdepth 1)"
  [ -d "$only" ] || break
  root="$only"
done
[ "$root" != "$stage" ] && say "package root is ${root#"$stage"/}"

# ---- validate before touching the destination -------------------------------
entries="$(find "$root" -mindepth 1 -maxdepth 1 | wc -l | tr -d ' ')"
[ "$entries" -gt 0 ] || die "the archive unpacked to nothing usable"
[ -w "$here" ] || die "cannot write to $here"

manifest="$root/DELETE.txt"
deletions=()
if [ -f "$manifest" ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%%#*}"; line="$(printf '%s' "$line" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [ -n "$line" ] || continue
    case "$line" in
      /*|*/../*|../*|*/..|..) die "DELETE.txt entry escapes the install directory: $line" ;;
    esac
    deletions+=("$line")
  done < "$manifest"
fi

say "$entries item(s) to install into $here"
[ "${#deletions[@]}" -gt 0 ] && say "${#deletions[@]} path(s) listed for removal"

if [ "$dry_run" = 1 ]; then
  say "dry run, nothing written. Would install:"
  (cd "$root" && find . -mindepth 1 -maxdepth 1 ! -name DELETE.txt \
     -exec basename {} \; | sort | sed 's/^/  /')
  [ "${#deletions[@]}" -gt 0 ] && printf '  (delete) %s\n' "${deletions[@]}"
  exit 0
fi

# ---- install ----------------------------------------------------------------
if [ "$backup" = 1 ]; then
  stamp="$(date +%Y%m%d-%H%M%S)"
  bak="$here/.prompt-bench-backup-$stamp"
  mkdir -p "$bak"
  (cd "$root" && find . -mindepth 1 -maxdepth 1) | while IFS= read -r item; do
    name="${item#./}"
    [ -e "$here/$name" ] && cp -a "$here/$name" "$bak/" 2>/dev/null || true
  done
  say "existing copies saved in $(basename "$bak")"
fi

rm -f "$root/DELETE.txt"

# Live data wins over the patch's copy.
for keep in uploads/unlock-codes.db; do
  if [ -e "$here/$keep" ] && [ -e "$root/$keep" ]; then
    rm -f "$root/$keep"
    say "kept the server's own $keep"
  fi
done

# Remember who owns each folder that is already here, and put it back after the
# copy: cp -a would otherwise give every folder the patch's owner and mode.
owners="$tmp/owners"
: > "$owners"
(cd "$root" && find . -mindepth 1 -type d) | while IFS= read -r d; do
  d="${d#./}"
  # An if, not &&: a folder that does not exist yet must not end the loop on
  # a failed test, which set -e would turn into a silent abort.
  if [ -d "$here/$d" ]; then
    printf '%s\t%s\n' "$(stat -c '%u:%g %a' "$here/$d")" "$d" >> "$owners"
  fi
done

cp -a "$root/." "$here/" || die "could not copy the patch into $here"

while IFS="$(printf '\t')" read -r meta d; do
  [ -n "$d" ] || continue
  chown "${meta%% *}" "$here/$d" 2>/dev/null || true
  chmod "${meta##* }" "$here/$d" 2>/dev/null || true
done < "$owners"

for path in "${deletions[@]+"${deletions[@]}"}"; do
  target="$here/$path"
  if [ -e "$target" ]; then
    rm -rf -- "$target" && say "removed $path"
  fi
done

# The members database lives in data/, which the container must be able to
# write, exactly like uploads/. Create it once, with uploads' owner.
if [ ! -d "$here/data" ]; then
  mkdir -p "$here/data"
  if [ -d "$here/uploads" ]; then
    chown "$(stat -c '%u:%g' "$here/uploads")" "$here/data" 2>/dev/null || true
  fi
  chmod 700 "$here/data" 2>/dev/null || true
  say "made data/ for the members database"
fi

say "done. Prompt Bench updated in $here"

exit 0
}

#!/usr/bin/env bash
# Prompt Bench public bootstrap installer.
# Downloads the current public repository into the current directory.
set -euo pipefail

repo='flyinggoatman/prompt-bench'
branch='main'
target="${1:-$PWD}"
tmp=''

die() { printf 'Prompt Bench installer: %s\n' "$*" >&2; exit 1; }
say() { printf 'Prompt Bench installer: %s\n' "$*"; }
cleanup() { [ -n "$tmp" ] && [ -d "$tmp" ] && rm -rf "$tmp"; }
trap cleanup EXIT INT TERM

command -v curl >/dev/null 2>&1 || die 'curl is required.'
command -v tar >/dev/null 2>&1 || die 'tar is required.'

mkdir -p "$target"
target="$(cd "$target" && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/prompt-bench-public.XXXXXX")" || die 'could not create a temporary directory.'
archive="$tmp/repo.tar.gz"
stage="$tmp/stage"
mkdir -p "$stage"

say "downloading public Prompt Bench from $repo"
curl -fsSL \
  -H 'Accept: application/vnd.github+json' \
  -H 'X-GitHub-Api-Version: 2022-11-28' \
  "https://api.github.com/repos/$repo/tarball/$branch" \
  -o "$archive" || die 'download failed.'

listing="$(tar -tzf "$archive")" || die 'downloaded archive could not be read.'
[ -n "$listing" ] || die 'downloaded archive is empty.'
while IFS= read -r entry; do
  [ -n "$entry" ] || continue
  case "$entry" in
    /*|*/../*|../*|*/..|..) die "refusing unsafe archive entry: $entry" ;;
  esac
done <<< "$listing"

tar -xzf "$archive" -C "$stage" || die 'could not unpack the repository.'
root="$(find "$stage" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
[ -n "$root" ] && [ -d "$root" ] || die 'repository archive had no usable root directory.'

say "installing into $target"
cp -a "$root/." "$target/" || die 'could not copy Prompt Bench into the target directory.'
chmod +x "$target/install-public.sh" "$target/install.sh" 2>/dev/null || true

say 'done. Public Prompt Bench is installed or updated.'
say 'local files that are not part of the repository were left in place.'

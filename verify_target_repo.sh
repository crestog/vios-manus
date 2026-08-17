#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPECTED_REMOTE="https://github.com/crestog/vios-manus.git"
ORIGINAL_REPO_RE='(^|/)(VideoIntelligenceOS)(\.git)?$'

if [[ ! -d "$ROOT/.git" ]]; then
  echo "target safety check failed: not a git worktree: $ROOT" >&2
  exit 2
fi

remote_url="$(git -C "$ROOT" remote get-url origin 2>/dev/null || true)"
case "$remote_url" in
  "$EXPECTED_REMOTE"|"git@github.com:crestog/vios-manus.git") ;;
  *)
    echo "target safety check failed: origin is not crestog/vios-manus: $remote_url" >&2
    exit 3
    ;;
esac

while IFS= read -r url; do
  if [[ "$url" =~ $ORIGINAL_REPO_RE ]] || [[ "$url" == *"crestog/VideoIntelligenceOS"* ]]; then
    echo "target safety check failed: writable original-repository remote detected: $url" >&2
    exit 4
  fi
done < <(git -C "$ROOT" remote -v | awk '{print $2}' | sort -u)

head_sha="$(git -C "$ROOT" rev-parse HEAD)"
branch="$(git -C "$ROOT" branch --show-current)"
if [[ -z "$branch" ]]; then
  echo "target safety check failed: detached HEAD at $head_sha" >&2
  exit 5
fi

echo "target safety check passed: repository=crestog/vios-manus branch=$branch commit=$head_sha"

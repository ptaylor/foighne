#!/usr/bin/env bash
set -euo pipefail

# Publish foighne to GitHub Pages with automatic versioning.
# Copies foighne.html → public/index.html, bumps minor version, tags, commits, and pushes.
#
# Usage:
#   ./publish.sh              # bump version, copy, commit, tag, push
#   ./publish.sh --no-push    # copy only, don't commit or push

SRC="foighne.html"
PUB_DIR="public"
TARGET_BRANCH="${PUBLISH_BRANCH:-public}"
DEST="${PUB_DIR}/index.html"

NO_PUSH=false
if [[ "${1:-}" == "--no-push" ]]; then
  NO_PUSH=true
fi

# --- Determine next version ---
LATEST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "v0.0")
if [[ "$LATEST_TAG" =~ ^v([0-9]+)\.([0-9]+)$ ]]; then
  MAJOR="${BASH_REMATCH[1]}"
  MINOR="${BASH_REMATCH[2]}"
  NEXT_VERSION="v${MAJOR}.$((MINOR + 1))"
else
  NEXT_VERSION="v1.0"
fi

# --- Copy game to public/ with version + commit injected ---
COMMIT_HASH=$(git rev-parse --short HEAD)
mkdir -p "$PUB_DIR"
# Copy card back images
if [ -d images ]; then
  rm -rf "$PUB_DIR/images"
  cp -r images "$PUB_DIR/images"
  echo "✔ Copied images/ → $PUB_DIR/images/"
fi
sed -e "s/content=\"VERSION\"/content=\"${NEXT_VERSION}\"/" \
    -e "s/content=\"COMMIT\"/content=\"${COMMIT_HASH}\"/" \
    "$SRC" > "$DEST"
echo "✔ Copied $SRC → $DEST (version ${NEXT_VERSION}, commit ${COMMIT_HASH})"

if $NO_PUSH; then
  echo "✔ Done (no push — run './publish.sh' to push)"
  exit 0
fi

# --- Commit, tag & push main ---
git add "$PUB_DIR"
if git diff --cached --quiet; then
  echo "✔ No changes to commit"
else
  git commit -m "Publish ${NEXT_VERSION}"
  echo "✔ Committed: Publish ${NEXT_VERSION}"
fi

git tag -a "$NEXT_VERSION" -m "Release ${NEXT_VERSION}"
echo "✔ Tagged ${NEXT_VERSION}"

git push origin main --tags
echo "✔ Pushed main + tags"

# --- Push public/ subtree to pages branch ---
git subtree push --prefix="$PUB_DIR" origin "$TARGET_BRANCH"
echo ""
echo "🎉 Published ${NEXT_VERSION}! GitHub Pages deploys from: ${TARGET_BRANCH} / (root)"

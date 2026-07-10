#!/usr/bin/env bash
set -euo pipefail

# Publish foighne to GitHub Pages with automatic versioning.
#
# Usage:
#   ./publish.sh              # production: bump version, tag, push to root
#   ./publish.sh --test       # test: -test suffix, push to /test/ subdir, no tag
#   ./publish.sh --no-push    # copy only, don't commit or push

SRC="foighne.html"
PUB_DIR="public"
TARGET_BRANCH="${PUBLISH_BRANCH:-public}"

NO_PUSH=false
TEST_MODE=false
if [[ "${1:-}" == "--no-push" ]]; then
  NO_PUSH=true
elif [[ "${1:-}" == "--test" ]]; then
  TEST_MODE=true
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

if $TEST_MODE; then
  NEXT_VERSION="${NEXT_VERSION}-test"
  DEST_DIR="${PUB_DIR}/test"
else
  DEST_DIR="${PUB_DIR}"
fi

DEST="${DEST_DIR}/index.html"

# --- Copy game with version + commit injected ---
COMMIT_HASH=$(git rev-parse --short HEAD)
mkdir -p "$DEST_DIR"
# Copy card back images
if [ -d images ]; then
  rm -rf "$DEST_DIR/images"
  cp -r images "$DEST_DIR/images"
  echo "✔ Copied images/ → $DEST_DIR/images/"
fi
sed -e "s/content=\"VERSION\"/content=\"${NEXT_VERSION}\"/" \
    -e "s/content=\"COMMIT\"/content=\"${COMMIT_HASH}\"/" \
    "$SRC" > "$DEST"
echo "✔ Copied $SRC → $DEST (version ${NEXT_VERSION}, commit ${COMMIT_HASH})"

if $NO_PUSH; then
  echo "✔ Done (no push — run './publish.sh' to push)"
  exit 0
fi

# --- Commit published files (force-add since public/ is gitignored) ---
git add -f "$DEST_DIR"
git commit --no-verify -m "publish ${NEXT_VERSION}" || echo "⚠ Nothing to commit"

# --- Push main ---
git push
echo "✔ Pushed main"

# --- Tag release (production only) ---
if ! $TEST_MODE; then
  git tag -a "$NEXT_VERSION" -m "Release ${NEXT_VERSION}"
  echo "✔ Tagged ${NEXT_VERSION}"
  git push origin --tags
  echo "✔ Pushed tags"
fi

# --- Push public/ subtree to pages branch ---
git push origin $(git subtree split --prefix="$PUB_DIR"):"$TARGET_BRANCH" --force
echo ""
if $TEST_MODE; then
  echo "🧪 Test published: https://ptaylor.github.io/foighne/test/"
else
  echo "🎉 Published ${NEXT_VERSION}! https://ptaylor.github.io/foighne/"
fi

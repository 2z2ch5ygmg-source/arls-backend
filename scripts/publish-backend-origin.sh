#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE_NAME="${1:-backend-origin}"
REMOTE_URL="$(git -C "$ROOT_DIR" remote get-url "$REMOTE_NAME")"
TMP_DIR="$(mktemp -d)"
SOURCE_MODE="root"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

if [[ -d "$ROOT_DIR/backend/app" && -f "$ROOT_DIR/backend/Dockerfile" ]]; then
  SOURCE_MODE="backend-subdir"
fi

git clone --branch main "$REMOTE_URL" "$TMP_DIR/repo" >/dev/null 2>&1

find "$TMP_DIR/repo" -mindepth 1 -maxdepth 1 \
  ! -name '.git' \
  -exec rm -rf {} +

copy_into_repo() {
  local src="$1"
  local dest="$TMP_DIR/repo"
  if [[ -d "$src" ]]; then
    cp -R "$src" "$dest/"
  elif [[ -f "$src" ]]; then
    cp "$src" "$dest/"
  fi
}

if [[ "$SOURCE_MODE" == "backend-subdir" ]]; then
  for path in \
    "$ROOT_DIR/backend/.github" \
    "$ROOT_DIR/backend/app" \
    "$ROOT_DIR/backend/migrations" \
    "$ROOT_DIR/backend/scripts" \
    "$ROOT_DIR/backend/tests" \
    "$ROOT_DIR/backend/Dockerfile" \
    "$ROOT_DIR/backend/README.md" \
    "$ROOT_DIR/backend/requirements.txt"
  do
    copy_into_repo "$path"
  done
else
  for path in \
    "$ROOT_DIR/.github" \
    "$ROOT_DIR/app" \
    "$ROOT_DIR/migrations" \
    "$ROOT_DIR/scripts" \
    "$ROOT_DIR/tests" \
    "$ROOT_DIR/Dockerfile" \
    "$ROOT_DIR/README.md" \
    "$ROOT_DIR/requirements.txt"
  do
    copy_into_repo "$path"
  done
fi

find "$TMP_DIR/repo" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$TMP_DIR/repo" -name '.pytest_cache' -type d -prune -exec rm -rf {} +
find "$TMP_DIR/repo" -name '.DS_Store' -delete

if git -C "$TMP_DIR/repo" diff --quiet && git -C "$TMP_DIR/repo" diff --cached --quiet; then
  echo "backend-origin에 푸시할 변경이 없습니다."
  exit 0
fi

git -C "$TMP_DIR/repo" config user.name "$(git -C "$ROOT_DIR" config user.name)"
git -C "$TMP_DIR/repo" config user.email "$(git -C "$ROOT_DIR" config user.email)"
git -C "$TMP_DIR/repo" add .
git -C "$TMP_DIR/repo" commit -m "sync: publish backend from integrated workspace"
git -C "$TMP_DIR/repo" push origin main

echo "backend-origin main 브랜치에 백엔드 소스 동기화 완료"

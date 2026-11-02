#!/bin/sh
# Regenerates the user-guide screenshots (frontend/public/guide/<lang>/img/*.webp)
# from a throwaway SQLite instance on port 8001 with fictional demo people,
# one fresh instance per language, then rebuilds the guide pages.
# Usage: docs/guide-tools/regenerate.sh [ru en de ...]   (default: every content/*.json)
# Needs google-chrome, uv and a built frontend/dist.
set -e
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
TOOLS="$ROOT/docs/guide-tools"
LANGS=${*:-$(cd "$TOOLS/content" && ls *.json | sed 's/\.json$//')}
RUN="uv run --with playwright --with pyotp --with httpx --with pillow python"
cd "$ROOT/backend"
for L in $LANGS; do
  WORK=$(mktemp -d)
  mkdir -p "$WORK/shots" "$WORK/data"
  export PLANNER_DATABASE_URL="sqlite+aiosqlite:///$WORK/guide.db" PLANNER_STATIC_DIR="$ROOT/frontend/dist" \
         PLANNER_DATA_DIR="$WORK/data" PLANNER_BASE_URL=http://localhost:8001 PLANNER_SCHEDULER_MINUTES=0
  .venv/bin/alembic upgrade head > "$WORK/migrate.log" 2>&1
  .venv/bin/uvicorn app.main:app --port 8001 > "$WORK/server.log" 2>&1 &
  SERVER=$!
  trap 'kill $SERVER 2>/dev/null || true' EXIT
  sleep 4
  echo "== $L"
  $RUN "$TOOLS/p1_setup.py" "$WORK" "$L"
  $RUN "$TOOLS/p2_seed.py" "$WORK" "$L"
  $RUN "$TOOLS/p3_shots.py" "$WORK" "$L"
  mkdir -p "$ROOT/frontend/public/guide/$L/img"
  $RUN - "$WORK/shots" "$ROOT/frontend/public/guide/$L/img" <<'PY'
import sys, pathlib
from PIL import Image
src, dst = map(pathlib.Path, sys.argv[1:])
for f in sorted(src.glob("*.png")):
    Image.open(f).save(dst / (f.stem + ".webp"), "WEBP", quality=82, method=6)
print("webp", len(list(src.glob("*.png"))))
PY
  kill $SERVER; wait $SERVER 2>/dev/null || true
  rm -rf "$WORK"
done
python3 "$TOOLS/build_guide.py"

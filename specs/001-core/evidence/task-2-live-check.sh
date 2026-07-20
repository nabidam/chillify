#!/usr/bin/env bash
# Drive Task 2's acceptance behaviour against a real uvicorn process.
set -Eeuo pipefail

REPO=/home/dev/projects/chillify
ROOT=$(mktemp -d /home/dev/projects/chillify/backend/.live-XXXXXX)
export CHILLIFY_DATA_ROOT="$ROOT/data"
export CHILLIFY_MUSIC_ROOT="$ROOT/music"
mkdir -p "$CHILLIFY_DATA_ROOT/db" "$CHILLIFY_MUSIC_ROOT/Music/sigur ros/takk"
export REDIS_URL="redis://127.0.0.1:6379/9"
export CHILLIFY_ENV=production
cd "$REPO/backend"
export CHILLIFY_SECRET_KEY=$(uv run python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())")

cleanup() { [[ -n "${API_PID:-}" ]] && kill "$API_PID" 2>/dev/null; rm -rf "$ROOT"; }
trap cleanup EXIT

echo "== migrate"
uv run alembic upgrade head 2>&1 | tail -2

echo "== seed one managed track and its file"
uv run python - <<'PY'
import hashlib, os, uuid
from pathlib import Path
from sqlalchemy import text
from chillify.domain.models import to_rfc3339
from chillify.infrastructure.db.engine import create_database_engine
from datetime import UTC, datetime

music = Path(os.environ["CHILLIFY_MUSIC_ROOT"])
rel = "Music/sigur ros/takk/hoppipolla.mp3"
content = b"\xff\xfb\x90\x64" + bytes(range(256)) * 128
(music / rel).write_bytes(content)

engine = create_database_engine(Path(os.environ["CHILLIFY_DATA_ROOT"]) / "db" / "chillify.sqlite3")
now = to_rfc3339(datetime.now(UTC))
with engine.begin() as c:
    c.execute(text(
        "INSERT INTO tracks (id,title,artist,album,release_year,disc_number,track_number,"
        "duration_ms,normalized_artist,normalized_title,normalized_album,file_relpath,"
        "mime_type,file_size_bytes,content_sha256,availability,revision,created_at,updated_at)"
        " VALUES (:i,'Hoppipolla','Sigur Rós','Takk...',2005,1,4,268000,'sigur ros',"
        "'hoppipolla','takk',:r,'audio/mpeg',:s,:d,'available',1,:n,:n)"),
        {"i": str(uuid.uuid7()), "r": rel, "s": len(content),
         "d": hashlib.sha256(content).hexdigest(), "n": now})
print("seeded", len(content), "bytes")
PY

echo "== start uvicorn"
uv run uvicorn chillify.api.main:app --port 8099 --log-level warning &
API_PID=$!
for _ in $(seq 1 40); do
    curl -sf http://127.0.0.1:8099/api/v1/system/health >/dev/null && break
    sleep 0.25
done

echo "== GET /system/health"
curl -s http://127.0.0.1:8099/api/v1/system/health

echo; echo "== POST /profiles"
curl -s -X POST http://127.0.0.1:8099/api/v1/profiles \
    -H 'Content-Type: application/json' -d '{"name":"  Household  "}'

echo; echo "== POST /profiles (duplicate)"
curl -s -o /dev/stderr -w '  HTTP %{http_code}\n' -X POST http://127.0.0.1:8099/api/v1/profiles \
    -H 'Content-Type: application/json' -d '{"name":"HOUSEHOLD"}'

echo "== GET /profiles"
curl -s http://127.0.0.1:8099/api/v1/profiles

echo; echo "== GET /library/tracks"
TRACK_ID=$(curl -s http://127.0.0.1:8099/api/v1/library/tracks | tee /dev/stderr | uv run python -c 'import json,sys;print(json.load(sys.stdin)["items"][0]["id"])')

echo; echo "== GET /library/tracks?q=Sigur%20Rós (accent-folded search)"
curl -s --get --data-urlencode 'q=Sigur Rós' http://127.0.0.1:8099/api/v1/library/tracks \
    | uv run python -c 'import json,sys;print("matches:",len(json.load(sys.stdin)["items"]))'

echo "== GET /tracks/{id}/stream (full)"
curl -s -D - -o /dev/null "http://127.0.0.1:8099/api/v1/tracks/$TRACK_ID/stream" \
    | grep -iE '^(HTTP|content-type|content-length|accept-ranges|etag)'

echo "== GET /tracks/{id}/stream (Range: bytes=100-199)"
curl -s -D - -o /tmp/range.bin -H 'Range: bytes=100-199' \
    "http://127.0.0.1:8099/api/v1/tracks/$TRACK_ID/stream" \
    | grep -iE '^(HTTP|content-range|content-length)'
echo "  received $(stat -c%s /tmp/range.bin) bytes"

echo "== restart the API, then read the same data back"
kill "$API_PID"; wait "$API_PID" 2>/dev/null || true
uv run uvicorn chillify.api.main:app --port 8099 --log-level warning &
API_PID=$!
for _ in $(seq 1 40); do
    curl -sf http://127.0.0.1:8099/api/v1/system/health >/dev/null && break
    sleep 0.25
done
echo "  profiles after restart: $(curl -s http://127.0.0.1:8099/api/v1/profiles | uv run python -c 'import json,sys;print([p["name"] for p in json.load(sys.stdin)["items"]])')"
echo "  tracks after restart:   $(curl -s http://127.0.0.1:8099/api/v1/library/tracks | uv run python -c 'import json,sys;print([t["title"] for t in json.load(sys.stdin)["items"]])')"

echo "== delete the managed file, then stream it"
rm "$CHILLIFY_MUSIC_ROOT/$(uv run python -c "print('Music/sigur ros/takk/hoppipolla.mp3')")"
curl -s -o /dev/stderr -w '  HTTP %{http_code}\n' "http://127.0.0.1:8099/api/v1/tracks/$TRACK_ID/stream"
echo "  availability now: $(curl -s http://127.0.0.1:8099/api/v1/library/tracks | uv run python -c 'import json,sys;t=json.load(sys.stdin)["items"][0];print(t["availability"], "is_playable=", t["is_playable"])')"

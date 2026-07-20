#!/usr/bin/env bash
#
# Regenerate frontend/src/api/generated.ts from the served OpenAPI document.
#
#   ./scripts/generate_api_types.sh
#
# The document comes from the real FastAPI application rather than a checked-in
# copy, so the browser's types cannot drift from the routes that serve them. The
# result is committed; it is never hand-edited.

set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$REPO_ROOT/backend"
FRONTEND="$REPO_ROOT/frontend"
DOCUMENT="$(mktemp -t chillify-openapi-XXXXXX.json)"
trap 'rm -f "$DOCUMENT"' EXIT

(cd "$BACKEND" && uv run python -c '
import json
import sys

from chillify.api.main import create_app

sys.stdout.write(json.dumps(create_app().openapi(), indent=2, sort_keys=True))
') > "$DOCUMENT"

# Biome deliberately excludes the generated file, so it is written exactly as
# the generator emits it and stays a byte-for-byte regeneration artifact.
(cd "$FRONTEND" && ./node_modules/.bin/openapi-typescript "$DOCUMENT" -o src/api/generated.ts)

printf 'generated: frontend/src/api/generated.ts\n'

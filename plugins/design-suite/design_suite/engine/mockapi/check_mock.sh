#!/usr/bin/env bash
#
# check_mock.sh — one-command sanity check for your Postman mock server.
#
# Run this BEFORE launching the app whenever you've (re)created a mock server,
# re-imported the collection, or changed DEV_BASE_URL. It probes the sign-in-
# critical endpoints plus a couple of GETs and tells you, per endpoint, whether
# the mock is actually serving them — turning the "app won't sign in" black box
# into a concrete diagnosis.
#
# It distinguishes the two failure modes we've actually hit:
#   * mockNotFoundError  — the whole mock server is gone (deleted/regenerated);
#                          your DEV_BASE_URL points at a dead mock.
#   * 404 on a /v1 path  — the mock is alive but not matching this request;
#                          usually a stale saved-example `originalRequest`
#                          (run `/audit-mock-api`, and look for
#                          `postman_original_request_stale`).
#
# Usage:
#   "${CLAUDE_PLUGIN_ROOT}/design_suite/engine/mockapi/check_mock.sh"
#       uses DEV_BASE_URL from .env
#   "${CLAUDE_PLUGIN_ROOT}/design_suite/engine/mockapi/check_mock.sh" https://<id>.mock.pstmn.io
#       probe a URL directly
#
# Exit code is non-zero if any probed endpoint fails, so it's CI/pre-run safe.

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# ── Resolve the base URL: explicit arg wins, else DEV_BASE_URL from .env ──────
BASE_URL="${1:-}"
if [ -z "$BASE_URL" ]; then
  ENV_FILE="$REPO_ROOT/.env"
  if [ ! -f "$ENV_FILE" ]; then
    echo "✗ No .env at $ENV_FILE and no URL argument given." >&2
    echo "  Usage: $0 [https://<id>.mock.pstmn.io]" >&2
    exit 2
  fi
  # Read only the DEV_BASE_URL line; strip key=, quotes, whitespace, trailing /.
  BASE_URL="$(grep -E '^[[:space:]]*DEV_BASE_URL[[:space:]]*=' "$ENV_FILE" \
    | tail -1 | sed -E 's/^[^=]*=//' | tr -d '"'"'"' \r' | sed -E 's#[[:space:]]*$##; s#/*$##')"
  if [ -z "$BASE_URL" ]; then
    echo "✗ DEV_BASE_URL is not set in $ENV_FILE." >&2
    exit 2
  fi
fi

echo "Probing mock at: $BASE_URL"
echo

# ── Endpoints to probe: "METHOD PATH" ────────────────────────────────────────
# The two sign-in-critical calls first (auth_remote_datasource.dart), then a
# couple of representative GETs. Not exhaustive — a passing run means the mock
# is live and matching /v1 paths, which is the failure class this catches.
PROBES=(
  "POST /v1/auth/oauth"
  "GET /v1/users/me"
  "GET /v1/notifications"
  "GET /v1/care-plan/current"
)

failures=0

for probe in "${PROBES[@]}"; do
  method="${probe%% *}"
  path="${probe#* }"
  url="${BASE_URL}${path}"

  if [ "$method" = "POST" ]; then
    resp="$(curl -s -m 15 -w $'\n%{http_code}' -X POST "$url" \
      -H 'Content-Type: application/json' \
      -H 'Authorization: Bearer sanity-check' \
      -d '{"provider":"google","idToken":"sanity-check"}' 2>/dev/null)"
  else
    resp="$(curl -s -m 15 -w $'\n%{http_code}' -X "$method" "$url" \
      -H 'Authorization: Bearer sanity-check' 2>/dev/null)"
  fi

  code="$(printf '%s' "$resp" | tail -1)"
  body="$(printf '%s' "$resp" | sed '$d')"

  label="$(printf '%-6s %s' "$method" "$path")"

  if [ -z "$code" ]; then
    echo "✗ $label — no response (connection failed / bad URL)"
    failures=$((failures + 1))
  elif printf '%s' "$body" | grep -qi 'mockNotFoundError'; then
    echo "✗ $label — mockNotFoundError: this mock server is gone. Recreate it in"
    echo "           Postman and update DEV_BASE_URL to the new mock URL."
    failures=$((failures + 1))
  elif [ "$code" = "200" ] || [ "$code" = "201" ]; then
    echo "✓ $label — $code"
  elif [ "$code" = "404" ]; then
    echo "✗ $label — 404: mock is alive but not matching this request. Likely a"
    echo "           stale saved-example originalRequest — run"
    echo "           /audit-mock-api and look for"
    echo "           postman_original_request_stale."
    failures=$((failures + 1))
  else
    echo "✗ $label — HTTP $code (unexpected)"
    failures=$((failures + 1))
  fi
done

echo
if [ "$failures" -eq 0 ]; then
  echo "All ${#PROBES[@]} probes passed — mock is live and matching /v1 paths."
  exit 0
else
  echo "$failures of ${#PROBES[@]} probes failed — see above before launching the app."
  exit 1
fi

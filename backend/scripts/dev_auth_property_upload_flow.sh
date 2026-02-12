#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8000}"
EMAIL="${EMAIL:-dev@example.com}"
PROPERTY_NAME="${PROPERTY_NAME:-My Property}"
PDF_PATH="${1:-}"

if [[ -z "${PDF_PATH}" ]]; then
  echo "Usage: $0 /absolute/path/to/file.pdf"
  exit 1
fi

if [[ ! -f "${PDF_PATH}" ]]; then
  echo "File not found: ${PDF_PATH}"
  exit 1
fi

COOKIE_JAR="$(mktemp)"
cleanup() {
  rm -f "${COOKIE_JAR}"
}
trap cleanup EXIT

echo "1) Requesting magic link for ${EMAIL}..."
REQUEST_JSON="$(curl -sS -X POST "${API_BASE_URL}/auth/request-link" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${EMAIL}\"}")"

MAGIC_LINK="$(printf "%s" "${REQUEST_JSON}" | sed -n 's/.*"magic_link":"\([^"]*\)".*/\1/p')"
if [[ -z "${MAGIC_LINK}" ]]; then
  echo "Failed to get magic_link. Response:"
  echo "${REQUEST_JSON}"
  exit 1
fi

echo "2) Verifying magic link and storing session cookie..."
VERIFY_JSON="$(curl -sS -c "${COOKIE_JAR}" "${API_BASE_URL}${MAGIC_LINK}")"
echo "Verified user: ${VERIFY_JSON}"

echo "3) Creating property: ${PROPERTY_NAME}..."
PROPERTY_JSON="$(curl -sS -b "${COOKIE_JAR}" -c "${COOKIE_JAR}" \
  -X POST "${API_BASE_URL}/properties" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"${PROPERTY_NAME}\"}")"

PROPERTY_ID="$(printf "%s" "${PROPERTY_JSON}" | sed -n 's/.*"id":\([0-9][0-9]*\).*/\1/p')"
if [[ -z "${PROPERTY_ID}" ]]; then
  echo "Failed to create property. Response:"
  echo "${PROPERTY_JSON}"
  exit 1
fi
echo "Created property_id=${PROPERTY_ID}"

echo "4) Uploading PDF to property..."
UPLOAD_JSON="$(curl -sS -b "${COOKIE_JAR}" -c "${COOKIE_JAR}" \
  -X POST "${API_BASE_URL}/documents/upload" \
  -F "property_id=${PROPERTY_ID}" \
  -F "file=@${PDF_PATH}")"
echo "Upload response: ${UPLOAD_JSON}"

echo "5) Fetching scoped timeline..."
TIMELINE_JSON="$(curl -sS -b "${COOKIE_JAR}" \
  "${API_BASE_URL}/timeline?property_id=${PROPERTY_ID}")"
echo "Timeline response: ${TIMELINE_JSON}"

echo "Done."

#!/bin/bash
# Start guard for the deployed Keycloak. Refuses to start when a setting the
# realm import depends on is missing, then hands over to Keycloak itself.
#
# WHY. `compose.keycloak.yaml` refuses to start with a secret unset (`:?`),
# but a platform running this image has no such check. If the service were
# recreated with an empty database and, say, KEYCLOAK_ADMIN_SEED_PASSWORD
# missing, the import would run once with that placeholder unfilled -- and a
# public admin account's password could end up as the literal
# `${KEYCLOAK_ADMIN_SEED_PASSWORD}` text that is readable in this
# repository. Import runs only on an empty database, so that would stick.
# Found by review, 2026-09-15.
set -euo pipefail

required=(
  KEYCLOAK_CLIENT_SECRET
  KEYCLOAK_SEED_PASSWORD
  KEYCLOAK_ADMIN_SEED_PASSWORD
  KEYCLOAK_PUBLIC_APP_URL
  KC_HOSTNAME
  KC_DB_URL
  KC_DB_USERNAME
  KC_DB_PASSWORD
)

missing=()
for name in "${required[@]}"; do
  if [ -z "${!name:-}" ]; then
    missing+=("$name")
  fi
done
if [ "${#missing[@]}" -gt 0 ]; then
  echo "Sanad Keycloak refuses to start. Not set: ${missing[*]}" >&2
  exit 1
fi

# The realm file appends "/auth/callback" to this value, so a trailing slash
# would register "https://host//auth/callback" and every sign-in would fail
# with "Invalid redirect uri".
case "$KEYCLOAK_PUBLIC_APP_URL" in
  */)
    echo "Sanad Keycloak refuses to start. KEYCLOAK_PUBLIC_APP_URL must not end with /" >&2
    exit 1
    ;;
esac

exec /opt/keycloak/bin/kc.sh "$@"

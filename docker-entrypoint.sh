#!/bin/sh
# ST-05. Bridges the hosting platform's conventions to config.Settings,
# and seeds the corpus on a genuinely empty volume.
set -eu

# --- port and host -------------------------------------------------------
# Railway (and most PaaS) hand the port in $PORT and require a bind on
# 0.0.0.0. config.Settings reads SERVER_PORT / SERVER_HOST. Translating
# here keeps app.py's 127.0.0.1 default intact for a laptop run -- see the
# note in the Dockerfile about why that default exists (ADR-13 / LD-07).
if [ -n "${PORT:-}" ] && [ -z "${SERVER_PORT:-}" ]; then
    SERVER_PORT="$PORT"
    export SERVER_PORT
fi

if [ -z "${SERVER_HOST:-}" ]; then
    # A container that binds 127.0.0.1 is unreachable from outside itself,
    # so a published port would silently do nothing.
    SERVER_HOST="0.0.0.0"
    export SERVER_HOST
fi

# --- the open-door warning ----------------------------------------------
# Loud on purpose. This is the exact combination -- reachable from
# elsewhere, no password -- that ADR-13 says is not safe, and the failure
# is silent otherwise: the app works perfectly and everyone can read it.
case "${SERVER_HOST}" in
    127.0.0.1|localhost|::1) ;;
    *)
        if [ -z "${ACCESS_PASSWORD:-}" ]; then
            echo "=========================================================" >&2
            echo "WARNING: Sanad is bound to ${SERVER_HOST} with NO PASSWORD." >&2
            echo "Every document in every workspace is readable by anyone"   >&2
            echo "who reaches this address. Set ACCESS_PASSWORD to close it." >&2
            echo "=========================================================" >&2
        fi
        ;;
esac

# --- seed the corpus on first boot only ---------------------------------
# Sanad builds a workspace from a FOLDER ON DISK and has no upload, so a
# fresh volume leaves the product with nothing to index. The image carries
# the documents at /app/seed-corpus (outside the volume, because Railway
# mounts volumes at start and would hide anything written at build time).
#
# Copied only when the destination does not exist. An operator who removes
# a seeded document keeps it removed; this never overwrites live data and
# never runs twice.
SEED_DIR="/app/seed-corpus"
CORPUS_DIR="${SANAD_CORPUS_DIR:-/app/data/corpus}"

if [ -d "$SEED_DIR" ] && [ ! -e "$CORPUS_DIR" ]; then
    echo "seeding corpus into ${CORPUS_DIR} (first boot: it did not exist)"
    mkdir -p "$(dirname "$CORPUS_DIR")"
    cp -r "$SEED_DIR" "$CORPUS_DIR"
    echo "seeded: $(find "$CORPUS_DIR" -type f | wc -l) file(s)"
else
    echo "corpus not seeded (already present, or no seed shipped)"
fi

exec "$@"

#!/bin/sh
# ST-05 (Railway hosting). Bridges the hosting platform's conventions to
# config.Settings, fixes ownership on a volume this image does not own,
# drops root before the app ever runs, and seeds the corpus on a genuinely
# empty volume.
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

# --- drop root, after fixing ownership on a volume this image does not own
#
# WHY THIS RUNS AT ALL, and it is a fact proven against the real deploy,
# not a guess. Railway's disk at /app/data is a persistent volume that
# outlives any one image: an older image wrote the live files there as
# root (before this image existed), so a fresh container that simply
# starts as `sanad` (uid 10001) inherits a directory it does not own and
# cannot write to -- Sync and the SQLite registry would fail on the very
# first write, on the one environment this image cannot be rebuilt
# against by hand.
#
# So the container STARTS as root (the image sets no USER), fixes
# ownership on exactly what is not already sanad's, then drops to sanad
# for the rest of the process's life via `setpriv`. The chown is scoped
# with `-not -user sanad` so an already-correct volume (a fresh one this
# image created, or a later boot of this same image) costs one stat per
# entry and changes nothing -- this is not a one-time migration hack, it
# runs on every boot because the volume can be swapped or restored
# independently of the image.
#
# `chown -h` (never dereferencing a symlink) so a crafted or coincidental
# symlink under the volume cannot redirect ownership changes outside it.
#
# GUARDED ON `id -u`, not on a marker file: if the container is ever run
# already as `sanad` (a future image that sets `USER sanad` again, or an
# operator override), this block is skipped entirely and the script falls
# straight through to `exec "$@"` below -- chown-ing as a non-root user
# would fail loudly and take the container down for no reason.
if [ "$(id -u)" = "0" ]; then
    if [ -d /app/data ]; then
        find /app/data -not -user sanad -exec chown -h sanad:sanad {} + 2>/dev/null || true
    fi
    # Re-exec THIS SAME SCRIPT as sanad rather than jumping straight to
    # "$@": every step below (the corpus seed in particular) must also run
    # as the unprivileged user, because a directory the seed step creates
    # as root would be root-owned and exactly reproduce the problem this
    # block just fixed. `id -u` reads non-zero on the re-entry, so this
    # branch is skipped the second time through and execution falls to
    # the seeding step and then `exec "$@"` below.
    exec setpriv --reuid=sanad --regid=sanad --clear-groups "$0" "$@"
fi

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
    # COPY THEN RENAME, rather than copying straight into place, because
    # the check above and the copy are not one step. PROVEN, not guessed:
    # two containers started against one volume both passed the `! -e`
    # test, the slower one's `cp -r` then died with "cannot create
    # directory: File exists", `set -e` killed the entrypoint, and the
    # container exited 1 -- a crash loop, the worst failure to debug from
    # a hosting dashboard. Railway overlaps an old and a new container
    # during a redeploy, so two boots CAN see the same disk.
    #
    # A rename is atomic and cannot half-happen: the loser of the race
    # finds the directory already there, deletes its own copy and carries
    # on booting. A partial `corpus.tmp.<pid>` left by a container killed
    # mid-copy is also removed here rather than mistaken for the corpus,
    # because it is named per-process and never read by the app.
    seed_tmp="${CORPUS_DIR}.tmp.$$"
    rm -rf "$seed_tmp"
    cp -r "$SEED_DIR" "$seed_tmp"
    if mv "$seed_tmp" "$CORPUS_DIR" 2>/dev/null; then
        echo "seeded: $(find "$CORPUS_DIR" -type f | wc -l) file(s)"
    else
        rm -rf "$seed_tmp"
        echo "corpus not seeded (another boot seeded it first)"
    fi
else
    echo "corpus not seeded (already present, or no seed shipped)"
fi

exec "$@"

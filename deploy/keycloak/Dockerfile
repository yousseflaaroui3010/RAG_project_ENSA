# The Keycloak that the published demo signs people in against.
#
# The Keycloak service is NOT linked to GitHub. It is uploaded from a
# four-file bundle, and this is the whole procedure (run from the
# repository root, with <bundle> any empty directory):
#
#     mkdir -p <bundle>/deploy/keycloak <bundle>/keycloak
#     cp deploy/keycloak/railway.json <bundle>/railway.json
#     cp deploy/keycloak/Dockerfile deploy/keycloak/start.sh <bundle>/deploy/keycloak/
#     cp keycloak/realm-sanad.json <bundle>/keycloak/
#     railway up <bundle> --path-as-root --service keycloak --ci
#
# `railway.json` MUST sit at the bundle's root: that is the copy Railway
# reads. It pins the Dockerfile path and declares NO health check here, in
# the repository where both are reviewable, instead of leaving them to
# whatever the service's dashboard happens to hold -- and the dashboard is
# invisible to everyone reading this repo. It also makes the difference
# from Sanad explicit: the repository's own root railway.json health-checks
# `/api/v1/health`, which Keycloak does not serve, so anyone who uploaded
# this image from the repository root instead of a bundle would watch the
# deploy be polled on a 404 and rolled back, taking sign-in down.
#
# NOT PROVEN, and the first version of this comment claimed it was.
# After an upload of exactly this bundle the service deployed fine and the
# realm answered 200, and Railway's manifest read `dockerfilePath
# deploy/keycloak/Dockerfile, healthcheckPath None, restartPolicy
# ON_FAILURE 10`. That is consistent with this file being used -- but it is
# ALSO exactly what the service's own `RAILWAY_DOCKERFILE_PATH` variable
# and Railway's defaults produce, so the manifest cannot tell the two
# apart. Railway's documentation says a config file at the deployed root is
# picked up automatically, and the deployment details page marks settings
# that came from one with a file icon; that page is the only place the
# question can be settled, and nobody has looked yet. Keep the file: it is
# correct either way and costs nothing.
#
# TRAP: on that service, changing ANY variable without `--skip-deploys`
# makes Railway redeploy the plain published image, which has no start
# command and only prints help. After changing a variable there, upload
# this image again with `railway up`.
#
# THE BUNDLE IS FOUR FILES, and `railway.json` beside this one is the
# fourth, copied to the bundle's ROOT:
#     <bundle>/railway.json                     (deploy/keycloak/railway.json)
#     <bundle>/deploy/keycloak/Dockerfile       (this file)
#     <bundle>/deploy/keycloak/start.sh
#     <bundle>/keycloak/realm-sanad.json
# uploaded with `railway up <bundle> --path-as-root --service keycloak`.
# Its railway.json is what stops the REPOSITORY's root railway.json from
# applying here: that one health-checks `/api/v1/health`, which is Sanad's
# route and not Keycloak's, so a Keycloak deploy would be polled on a 404
# and rolled back -- taking sign-in down with it (review, 2026-09-16).
# Keycloak's own health lives on management port 9000, which a Railway
# HTTP health check on the app port cannot reach, so it declares none.
#
# WHY A DOCKERFILE AND NOT JUST THE PUBLISHED IMAGE. The official image has
# an ENTRYPOINT (`kc.sh`) and NO CMD, so a platform that starts it without
# arguments gets Keycloak's help text and an exited container -- which is
# exactly what Railway produced on 2026-09-15 before this file existed.
# Baking the command in also bakes in the realm, so the deployed realm and
# the one a developer gets from `compose.keycloak.yaml` are the same file.
#
# SETTINGS THAT LIVE ONLY ON THE PLATFORM, because they are secrets or
# depend on where it is deployed. start.sh refuses to start without each:
#   KEYCLOAK_CLIENT_SECRET        same value as Sanad's KEYCLOAK_CLIENT_SECRET
#   KEYCLOAK_SEED_PASSWORD        curator, reader and no-role demo people
#   KEYCLOAK_ADMIN_SEED_PASSWORD  the admin demo person
#   KEYCLOAK_PUBLIC_APP_URL       Sanad's public origin, no trailing slash;
#                                 must match Sanad's KEYCLOAK_REDIRECT_URL
#   KC_HOSTNAME                   this Keycloak's own public https URL
#   KC_DB_URL, KC_DB_USERNAME, KC_DB_PASSWORD   its Postgres
# Also needed on first boot only: KC_BOOTSTRAP_ADMIN_USERNAME and
# KC_BOOTSTRAP_ADMIN_PASSWORD (the realm administrator).

FROM quay.io/keycloak/keycloak:26.4

# The one source of truth for the realm, shared with the dev compose file.
# Placeholders inside it are filled from the environment at import time, so
# no secret is committed here either.
COPY keycloak/realm-sanad.json /opt/keycloak/data/import/realm-sanad.json
COPY --chmod=755 deploy/keycloak/start.sh /opt/keycloak/bin/sanad-start.sh

# Do the expensive server build now rather than on every boot. `start`
# then runs with --optimized, which skips re-deriving the configuration.
# The database vendor has to be known at build time for this to help.
ENV KC_DB=postgres
ENV KC_HEALTH_ENABLED=true
RUN /opt/keycloak/bin/kc.sh build

# Not secrets and not deployment-specific: behind a TLS-ending proxy that
# forwards plain http on port 8080. In the repository so they are reviewed.
ENV KC_HTTP_ENABLED=true
ENV KC_HTTP_PORT=8080
ENV KC_PROXY_HEADERS=xforwarded

# MEMORY, learned on Railway's trial plan on 2026-09-15, three ways:
# - Keycloak's defaults (70% of the container for the heap) got the
#   container killed every ten seconds, mid-start.
# - Capping Metaspace (where Java keeps loaded code) at 128m died with
#   "OutOfMemoryError: Metaspace" on the first real sign-in. It needs 256m.
# - Adding a garbage-collector flag stopped the JVM starting at all
#   ("Multiple garbage collectors selected"): kc.sh already picks G1.
ENV JAVA_OPTS_KC_HEAP="-XX:MetaspaceSize=96M -XX:MaxMetaspaceSize=256m -XX:ReservedCodeCacheSize=64m -Xss512k -Xms64m -Xmx256m"

ENTRYPOINT ["/opt/keycloak/bin/sanad-start.sh"]
# Production mode, behind Railway's TLS proxy. Import creates the realm on
# the first boot against an empty database and is skipped on every boot
# after that, so redeploying never overwrites a real person's account.
CMD ["start", "--optimized", "--import-realm"]

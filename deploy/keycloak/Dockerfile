# The Keycloak that the published demo signs people in against.
#
# Built from the repository root as its context, selected on Railway with
# the service variable RAILWAY_DOCKERFILE_PATH=deploy/keycloak/Dockerfile,
# and uploaded with `railway up` (the service is not linked to GitHub).
#
# TRAP: on that service, changing ANY variable without `--skip-deploys`
# makes Railway redeploy the plain published image, which has no start
# command and only prints help. After changing a variable there, upload
# this image again with `railway up`.
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

# syntax=docker/dockerfile:1

# ST-05: the container image, ported from MB's proven build on
# feat/S1-ST-05-docker-deploy onto main's structure and adapted for
# Railway (docs/journal/DECISIONS.md, ST-05 rows). One image serves both
# targets -- `docker compose up` on a laptop (ADR-10, local-first) and a
# Railway deploy.
#
# READ THIS BEFORE EXPOSING THE CONTAINER ON A NETWORK. `app.py::main`
# binds 127.0.0.1 on purpose and says why: ADR-13 / LD-07, "single user,
# no authentication, and nothing about this server is safe to expose on a
# network." This image lets `SERVER_HOST` be overridden so a container can
# publish a port at all -- that is a requirement of running in a
# container, not permission to put it on the public internet.
# `config.access_password` (ui/access_gate.py) is the gate that makes a
# published instance survive that fact.
#
# WHY THIS IS A MULTI-STAGE BUILD, and it is a measurement rather than a
# style choice. `sentence-transformers` depends on torch, and torch's
# default Linux wheel carries the whole CUDA runtime -- `uv.lock` holds
# dozens of `nvidia-*` entries, none of which can execute here because no
# GPU is attached to this container on a laptop or on Railway. MB's first
# build of this image spent 9,936 SECONDS (2 h 46 m) exporting layers and
# then died on a builder-lease timeout, read from the build log.
#
# The first fix attempted was to install the CPU wheel over the CUDA one in
# a later layer. THAT MAKES THE IMAGE BIGGER, NOT SMALLER: a Docker layer
# only ever adds, so a file deleted in layer N+1 still occupies space in
# layer N, and the result carries BOTH builds of torch. Two stages is the
# fix that actually works -- the runtime stage copies the finished virtual
# environment and nothing else, so the discarded CUDA wheels never enter
# the shipped image at all.

# ---------------------------------------------------------------------------
# Stage 1: build the virtual environment and cache the model weights.
# Nothing from this stage ships except the two directories copied below.
# ---------------------------------------------------------------------------
FROM python:3.12.11-slim-bookworm AS builder

# `uv` is the project's package manager (ADR-10), pinned to the version
# this repo is developed against rather than `:latest`: an unpinned tool
# resolves to whatever is newest at build time, so an image that built
# yesterday can fail today on a stranger's release schedule.
COPY --from=ghcr.io/astral-sh/uv:0.8.7 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    # sentence-transformers and fastembed cache their weights here. Kept
    # inside the image (see the download step below) so a cold start does
    # not pull ~1 GB over the network before the first question.
    HF_HOME=/opt/models/hf \
    SENTENCE_TRANSFORMERS_HOME=/opt/models/st \
    FASTEMBED_CACHE_PATH=/opt/models/fastembed

WORKDIR /app

# `pyproject.toml`/`uv.lock` only -- no README.md. This stage never runs
# `uv sync` on the project itself (no console-script entry point exists;
# `app.py` is executed as a plain script), only `uv export` for the
# dependency set and `uv pip install` against it, so the project's own
# build metadata -- which is what would need `readme = "README.md"` -- is
# never built here.
COPY pyproject.toml uv.lock ./
# NO BUILD CACHE MOUNT, and this was decided against rather than
# forgotten. Railway rejects an anonymous one ("missing an id argument"),
# and then rejects a named one too unless the id is literally
# `s/<SERVICE_ID>-<name>` -- their documented format hardcodes ONE
# Railway service's id. This repo is cloned on two machines and also
# builds locally through `docker compose`, so a Railway service id baked
# into the Dockerfile would be wrong everywhere except one deploy of one
# account. A build cache is an optimisation; portability is not.
RUN set -eu; \
    # WHY NOT `uv sync`, AND WHY NOT `--no-install-package torch`.
    # Both were tried and both still downloaded the CUDA stack, because
    # `uv.lock` pins the `nvidia-*` wheels as their OWN entries, not just
    # as something torch drags in -- excluding `torch` leaves all of them
    # in the resolution.
    #
    # So the lock is EXPORTED and the GPU rows are filtered out of it,
    # then CPU torch is installed from PyTorch's own index. Every other
    # package still comes from the lockfile at its locked version, so
    # this is not a loosened dependency set -- it is the same set with
    # the GPU half removed and torch swapped for its CPU build.
    #
    # `uv sync` used to create this; it is created explicitly now that the
    # install goes through `uv pip` instead.
    uv venv /app/.venv; \
    uv export --frozen --no-dev --no-emit-project --no-hashes -o /tmp/req.txt; \
    # THE REGEX IS THE PART THAT WENT WRONG ONCE, so it is spelled out.
    # An earlier version required an OPERATOR straight after `nvidia-`,
    # which matches nothing against a real row such as
    # `nvidia-cudnn-cu13==9.20.0.48` (the character after `nvidia-` is a
    # letter) -- the filter silently dropped only torch and triton and
    # `--no-deps` then installed every CUDA wheel by name. It looked
    # correct when tested on a platform whose export has no nvidia rows to
    # begin with, which is why that test proved nothing. `nvidia-` is now
    # an open prefix; `torch` and `triton` stay anchored to an operator so
    # a future `torchvision` is not silently dropped.
    grep -vE '^nvidia-|^torch([=<>!~; ]|$)|^triton([=<>!~; ]|$)' \
        /tmp/req.txt > /tmp/req-cpu.txt; \
    dropped=$(( $(wc -l < /tmp/req.txt) - $(wc -l < /tmp/req-cpu.txt) )); \
    echo "dropped ${dropped} GPU-only requirement rows"; \
    # A build where the filter matched NOTHING is the exact silent
    # failure described above. Fail loudly instead of shipping several GB.
    if [ "$dropped" -lt 3 ]; then \
        echo "FATAL: expected the GPU filter to drop torch, triton and the" >&2; \
        echo "nvidia-* rows, but it dropped only ${dropped}. The filter is" >&2; \
        echo "not matching this platform's export -- see the note above." >&2; \
        exit 1; \
    fi; \
    # THE VERSION IS READ FROM uv.lock's OWN EXPORT, NOT HARDCODED, and
    # this is a fix for a real, proven failure, not defensive style. `uv`
    # ignores `[tool.uv.sources]` for a package that only ever arrives
    # TRANSITIVELY -- torch is pulled in by sentence-transformers, never
    # listed directly under `[project.dependencies]` -- so an unpinned
    # `uv pip install --index-url .../cpu torch` resolves whatever build
    # is newest on PyTorch's CPU index. Proven against this lockfile: that
    # command silently installs 2.14.0+cpu on Linux while `uv.lock` pins
    # 2.13.0, which is exactly the "one machine gets a different build"
    # drift ADR-10 exists to prevent. `pyproject.toml` and `uv.lock`
    # remain untouched either way; only this build step reads the pin out
    # of them instead of trusting the index's default.
    torch_version="$(grep -oE '^torch==[^ ;]+' /tmp/req.txt | head -1 | cut -d= -f3)"; \
    if [ -z "$torch_version" ]; then \
        echo "FATAL: no pinned torch==<version> line in the uv export;" >&2; \
        echo "cannot install a matching CPU wheel. Check uv.lock." >&2; \
        exit 1; \
    fi; \
    echo "installing CPU torch pinned to uv.lock's version: ${torch_version}"; \
    # CPU torch goes in FIRST, at the version uv.lock actually pins. By
    # the time the rest is installed, torch is already present and
    # satisfies `sentence-transformers`'s requirement, so nothing
    # re-resolves it and no GPU wheel is ever fetched.
    VIRTUAL_ENV=/app/.venv uv pip install \
        --index-url https://download.pytorch.org/whl/cpu "torch==${torch_version}"; \
    # `--no-deps` IS LOAD-BEARING. Without it `uv pip install -r`
    # RE-RESOLVES the whole set: it reads `sentence-transformers`, sees a
    # torch requirement, ignores the CPU build already sitting in the venv
    # and fetches the CUDA one from PyPI anyway. It is SAFE here for one
    # specific reason: `uv export` emits the FULLY RESOLVED transitive set
    # from uv.lock, every dependency already named with its locked
    # version -- there is nothing left for a resolver to discover, so
    # turning resolution off removes a chance to go wrong rather than a
    # safety net.
    VIRTUAL_ENV=/app/.venv uv pip install --no-deps -r /tmp/req-cpu.txt; \
    orphans="$(VIRTUAL_ENV=/app/.venv uv pip list --format=freeze \
        | sed -n 's/^\(nvidia-[a-z0-9-]*\)==.*/\1/p' | tr '\n' ' ')"; \
    if [ -n "$orphans" ]; then \
        echo "removing unreachable GPU runtime: $orphans"; \
        VIRTUAL_ENV=/app/.venv uv pip uninstall $orphans; \
    else \
        echo "no nvidia-* packages left to remove"; \
    fi; \
    # THE PIN IS ASSERTED, NOT JUST LOGGED. A future PyTorch CPU-index
    # change that ignores the exact version pin must fail this build
    # loudly, not ship a silently different torch than uv.lock records.
    installed="$(/app/.venv/bin/python -c 'import torch; print(torch.__version__)')"; \
    case "$installed" in \
        "${torch_version}"+*) ;; \
        *) \
            echo "FATAL: installed torch ${installed}, expected" >&2; \
            echo "${torch_version}+cpu* (uv.lock pins ${torch_version})." >&2; \
            exit 1 ;; \
    esac; \
    /app/.venv/bin/python -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available())"

# Model weights, baked in deliberately. The alternative -- download on
# first use -- makes the first question of every fresh container wait on a
# ~1 GB transfer, and fails outright in the strict-local/offline demo case
# (ADR-06, LD-06). It costs image size and buys a cold start that works
# with no network.
COPY config.py ./
RUN /app/.venv/bin/python -c "\
from sentence_transformers import SentenceTransformer; \
from fastembed import SparseTextEmbedding; \
from config import get_settings; \
s = get_settings(); \
SentenceTransformer(s.embedding_model); \
SparseTextEmbedding(model_name=s.embedding_sparse_model); \
print('model weights cached into the image')"

# ---------------------------------------------------------------------------
# Stage 2: the shipped image. No uv, no build cache, no discarded wheels.
# ---------------------------------------------------------------------------
FROM python:3.12.11-slim-bookworm AS runtime

RUN groupadd --system --gid 10001 sanad \
    && useradd --system --uid 10001 --gid sanad --create-home sanad

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/opt/models/hf \
    SENTENCE_TRANSFORMERS_HOME=/opt/models/st \
    FASTEMBED_CACHE_PATH=/opt/models/fastembed \
    # The venv is activated by PATH rather than by `uv run`, so the
    # runtime stage needs no package manager at all.
    PATH="/app/.venv/bin:$PATH" \
    HF_HUB_OFFLINE=1

WORKDIR /app

# The virtual environment bakes its own absolute path into the console
# scripts, so /app/.venv must land at the SAME path it was built at.
COPY --from=builder --chown=sanad:sanad /app/.venv /app/.venv
COPY --from=builder --chown=sanad:sanad /opt/models /opt/models
COPY --chown=sanad:sanad . .

# THE SEED CORPUS, FETCHED AT BUILD TIME RATHER THAN COMMITTED.
# Sanad builds a workspace by pointing at a FOLDER OF FILES ON DISK
# (`workspace.folder_path`); there is no upload anywhere in the UI. A
# fresh deploy therefore has nothing to index and no way for an operator
# to give it anything -- the product would come up empty and stay empty.
#
# MB's original ST-05 branch solved this by committing `data/corpus/` to
# git so Railway's git-filtered upload could see it (`data/` is otherwise
# fully git-ignored, LD-06). That is a recorded ST-05 DECISIONS row this
# port does NOT repeat: `data/` stays entirely git-ignored on main, and
# `scripts/corpus.py` -- the tracked fetcher ST-07 already built for this
# exact "data/ cannot cross machines through git" problem -- runs here
# instead, at build time, with network access. `verify` is ST-07's own
# exit gate: it FAILS THIS BUILD, not just a log line, if a fetched file
# is not one Sanad's own conversion ladder can actually read (a scan, a
# truncated download, ...) -- see scripts/corpus.py's module docstring.
#
# The result is moved OUTSIDE the volume mount point, at /app/seed-corpus,
# for the same reason MB's branch did: Railway mounts its volume at
# container start, which would hide anything written under /app/data at
# build time. `docker-entrypoint.sh` copies from here into the volume on
# first boot only.
#
# THE FETCH IS BEST-EFFORT, THE VERIFY IS NOT. PROVEN on Railway's builder,
# 2026-09-12: the very first source (the Labour Code on
# adala.justice.gov.ma, the Moroccan Ministry of Justice) timed out from
# Railway's build servers while it downloads fine from Morocco -- and a
# build that dies whenever a foreign government site is slow or blocks a
# region is a build nobody controls. The seed is also the least important
# thing in this image: the live Railway disk already holds the documents,
# the entrypoint copies the seed only onto an EMPTY volume, and in
# evidence-only mode Sync is refused, so a seeded corpus cannot even be
# indexed there. So:
#   * fetch fails  -> ship NO seed at all (never a partial one), say so
#                     loudly in the build log, and the entrypoint prints
#                     "no seed shipped" at boot;
#   * fetch works  -> `verify` still FAILS THE BUILD on a bad file, so a
#                     shipped seed is always one Sanad can read.
RUN set -eu; \
    if python scripts/corpus.py fetch; then \
        python scripts/corpus.py verify; \
        mv /app/data/corpus /app/seed-corpus; \
        chown -R sanad:sanad /app/seed-corpus; \
    else \
        echo "WARNING: corpus fetch failed (a source was unreachable from" >&2; \
        echo "this builder). The image ships WITHOUT a seed corpus; an" >&2; \
        echo "empty volume will start with no documents. See Dockerfile." >&2; \
    fi; \
    rm -rf /app/data; \
    mkdir -p /app/data; \
    chown -R sanad:sanad /app/data

# NO `VOLUME` INSTRUCTION HERE, AND THAT IS DELIBERATE.
# Railway's builder rejects the image outright if there is one: "docker
# VOLUME ... is not supported, use Railway Volumes". Every build from
# 2026-09-12 until this line was removed died at "scheduling build" for
# exactly this reason (BUILD-STATE). `tests/unit/test_packaging.py` now
# guards this: the suite fails, naming Railway, if `VOLUME` ever comes
# back or an anonymous `--mount=type=cache` reappears in this file.
#
# The persistence itself is declared where it belongs for each target:
# `compose.yaml` names a `sanad-data` volume, and on Railway a Volume is
# attached to the service at /app/data. Without one of those, `data/` --
# the corpus, the SQLite registry, the Qdrant collection, the parent store
# and the reports -- is lost on every redeploy.

EXPOSE 8000

# Railway injects $PORT and expects the process to bind it on 0.0.0.0.
# config.Settings reads SERVER_HOST / SERVER_PORT with no prefix, so the
# mapping is done in the entrypoint rather than in application code --
# app.py keeps its 127.0.0.1 default for anyone running it on a laptop.
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# NO `USER sanad` HERE, AND THAT IS ALSO DELIBERATE even though every
# process this image ever runs is unprivileged. Railway's persistent disk
# at /app/data can already be owned by root -- PROVEN against the live
# deploy, not assumed: a volume an older image wrote to as root stays
# root-owned across every later redeploy of a newer image, and `sanad`
# (uid 10001, no special capabilities) cannot write into a directory it
# does not own. The container therefore STARTS as root;
# `docker-entrypoint.sh` fixes ownership on exactly what the volume does
# not already give `sanad`, then re-execs itself under `sanad` via
# `setpriv` before the corpus seed step runs and long before `python
# app.py` ever imports application code or opens a socket. See that
# script's own comment for why this runs on every boot rather than once.
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=6 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2).read()"]

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["python", "app.py"]

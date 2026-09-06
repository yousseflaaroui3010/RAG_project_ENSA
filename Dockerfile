# ST-05: the container image. One image serves both targets --
# `docker compose up` on a laptop (the signed architecture's local-first
# case, ADR-10) and a Railway deploy.
#
# READ THIS BEFORE EXPOSING THE CONTAINER ON A NETWORK. `app.py::main`
# binds 127.0.0.1 on purpose and says why: ADR-13 / LD-07, "single user,
# no authentication, and nothing about this server is safe to expose on a
# network." This image lets `SERVER_HOST` be overridden so a container can
# publish a port at all -- that is a requirement of running in a
# container, not permission to put it on the public internet. There is
# still no login on any route.
#
# WHY THIS IS A MULTI-STAGE BUILD, and it is a measurement rather than a
# style choice. `sentence-transformers` depends on torch, and torch's
# default Linux wheel carries the whole CUDA runtime -- `uv.lock` holds 73
# `nvidia-*` entries, none of which can execute here because no GPU is
# attached to this container on a laptop or on Railway. The first build of
# this image spent 9,936 SECONDS (2 h 46 m) exporting layers and then died
# on a builder-lease timeout, read from the build log.
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
FROM python:3.12-slim AS builder

# `uv` is the project's package manager (ADR-10). Pinned to the version
# this repo is developed against rather than `:latest`: an unpinned tool
# resolves to whatever is newest at build time, so an image that built
# yesterday can fail today on a stranger's release schedule.
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /uvx /bin/

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

# One RUN, on purpose. The CUDA wheels are downloaded, replaced and
# resolved, filtered and installed WITHIN a single layer, so nothing that
# was discarded can survive into the shipped image. `pyproject.toml` and
# `uv.lock` are NOT edited: a developer running `uv sync` on their own
# machine gets exactly what they got before this file existed, and the
# deviation cannot leak out of the container.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    set -eu; \
    # WHY NOT `uv sync`, AND WHY NOT `--no-install-package torch`.
    # Both were tried and both still downloaded the CUDA stack, because
    # `uv.lock` pins the `nvidia-*` wheels as their OWN entries, not just
    # as something torch drags in -- excluding `torch` leaves all 73 of
    # them in the resolution. The build log showed it plainly: 349 MB of
    # cudnn, 403 MB of cublas, 204 MB of cufft, 188 MB of triton, none of
    # which can ever execute in this container.
    #
    # So the lock is EXPORTED and the GPU rows are filtered out of it,
    # then CPU torch is installed from PyTorch's own index. Every other
    # package still comes from the lockfile at its locked version, so
    # this is not a loosened dependency set -- it is the same set with
    # the GPU half removed and torch swapped for its CPU build. The
    # reported saving on a sentence-transformers image is roughly
    # 8.3 GB -> 1.75 GB.
    #
    # THE ONE HONEST DEVIATION, stated rather than buried: torch's exact
    # version here is chosen by the CPU index, not by uv.lock, because
    # the CPU wheels carry a `+cpu` local version that the pin cannot
    # match. `pyproject.toml` and `uv.lock` are untouched, so a developer
    # running `uv sync` on their own machine is unaffected; only the
    # container differs, and only for this one package.
    # `uv sync` used to create this; it is created explicitly now that the
    # install goes through `uv pip` instead.
    uv venv /app/.venv; \
    uv export --frozen --no-dev --no-emit-project --no-hashes -o /tmp/req.txt; \
    # THE REGEX IS THE PART THAT WENT WRONG, so it is spelled out.
    # The first version was `^(torch|nvidia-|triton)([=<>!~ ]|$)`, which
    # requires an OPERATOR straight after `nvidia-`. Real rows read
    # `nvidia-cudnn-cu13==9.20.0.48`, so the character after `nvidia-` is
    # a letter and nothing matched: on Linux the filter dropped only
    # torch and triton, and `--no-deps` then installed all 73 CUDA wheels
    # by name. It looked correct when tested on Windows purely because a
    # Windows export contains no nvidia rows to begin with -- the test
    # could not have failed, which is why it proved nothing.
    #
    # `nvidia-` is now an open prefix; `torch` and `triton` stay anchored
    # to an operator so a future `torchvision` is not silently dropped.
    grep -vE '^nvidia-|^torch([=<>!~; ]|$)|^triton([=<>!~; ]|$)' \
        /tmp/req.txt > /tmp/req-cpu.txt; \
    dropped=$(( $(wc -l < /tmp/req.txt) - $(wc -l < /tmp/req-cpu.txt) )); \
    echo "dropped ${dropped} GPU-only requirement rows"; \
    # A build where the filter matched NOTHING is the exact silent
    # failure described above. Fail loudly instead of shipping 5 GB.
    if [ "$dropped" -lt 3 ]; then \
        echo "FATAL: expected the GPU filter to drop torch, triton and the" >&2; \
        echo "nvidia-* rows, but it dropped only ${dropped}. The filter is" >&2; \
        echo "not matching this platform's export -- see the note above." >&2; \
        exit 1; \
    fi; \
    # ORDER IS THE WHOLE FIX, and it was got wrong once. Installing the
    # filtered requirements FIRST does not work: `sentence-transformers`
    # declares torch as a dependency, so removing torch from the file
    # just makes the resolver fetch it from PyPI -- the CUDA build,
    # 502 MB of it, plus every `nvidia-*` wheel underneath. Watched
    # happening in build log #6.
    #
    # CPU torch goes in FIRST. By the time the rest is installed, torch
    # is already present and satisfies `sentence-transformers`'s
    # requirement, so nothing re-resolves it and no GPU wheel is ever
    # fetched.
    VIRTUAL_ENV=/app/.venv uv pip install \
        --index-url https://download.pytorch.org/whl/cpu torch; \
    # `--no-deps` IS LOAD-BEARING, and this is the third attempt at this
    # line. Without it `uv pip install -r` RE-RESOLVES the whole set: it
    # reads `sentence-transformers`, sees a torch requirement, ignores the
    # CPU build already sitting in the venv and fetches the CUDA one from
    # PyPI anyway. Watched happening in build log #7 -- nvidia downloads
    # went from 0 to 7 the moment this line ran.
    #
    # It is SAFE here for one specific reason: `uv export` emits the
    # FULLY RESOLVED transitive set from uv.lock -- 526 rows, every
    # dependency already named with its locked version. There is nothing
    # left for a resolver to discover, so turning resolution off removes
    # a chance to go wrong rather than a safety net.
    VIRTUAL_ENV=/app/.venv uv pip install --no-deps -r /tmp/req-cpu.txt; \
    orphans="$(VIRTUAL_ENV=/app/.venv uv pip list --format=freeze \
        | sed -n 's/^\(nvidia-[a-z0-9-]*\)==.*/\1/p' | tr '\n' ' ')"; \
    if [ -n "$orphans" ]; then \
        echo "removing unreachable GPU runtime: $orphans"; \
        VIRTUAL_ENV=/app/.venv uv pip uninstall $orphans; \
    else \
        echo "no nvidia-* packages left to remove"; \
    fi; \
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
FROM python:3.12-slim AS runtime

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
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /opt/models /opt/models

COPY . .

# THE SEED CORPUS, AND WHY IT IS NOT SIMPLY COPIED INTO /app/data.
# Sanad builds a workspace by pointing at a FOLDER OF FILES ON DISK
# (`workspace.folder_path`); there is no upload anywhere in the UI. A
# fresh deploy therefore has nothing to index and no way for an operator
# to give it anything -- the product would come up empty and stay empty.
#
# Copying the PDFs to /app/data at build time does NOT solve it, and this
# is Railway's documented behaviour rather than a guess: "Volumes are
# mounted to your service's container when it starts, not during build
# time. If you write data to a directory at build time, it will not
# persist on the volume." The mount would simply hide whatever the image
# had put there.
#
# So the files land OUTSIDE the volume, at /app/seed-corpus, and
# docker-entrypoint.sh copies them in on first boot only -- when the
# volume is empty. An operator who deletes a seeded document keeps it
# deleted; nothing here overwrites live data.
COPY data/corpus /app/seed-corpus

# `data/` is git-ignored (the corpus, the SQLite registry, the Qdrant
# collection, the parent store and the reports all live here). It is a
# VOLUME so the container can be rebuilt without losing an indexed
# workspace. On Railway this must be an attached volume mounted at
# /app/data, or every deploy starts with an empty registry.
VOLUME ["/app/data"]

EXPOSE 8000

# Railway injects $PORT and expects the process to bind it on 0.0.0.0.
# config.Settings reads SERVER_HOST / SERVER_PORT with no prefix, so the
# mapping is done in the entrypoint rather than in application code --
# app.py keeps its 127.0.0.1 default for anyone running it on a laptop.
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["python", "app.py"]

# All base image indexes are pinned. Refresh these alongside uv.lock/npm locks.
FROM node:22-bookworm-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392 AS studio
WORKDIR /build
COPY packages/client/package*.json packages/client/tsconfig.json ./packages/client/
COPY packages/client/src ./packages/client/src
RUN npm --prefix packages/client ci && npm --prefix packages/client run build
COPY studio/frontend/package*.json ./studio/frontend/
RUN npm --prefix studio/frontend ci
COPY studio/frontend ./studio/frontend
COPY studio/shared ./studio/shared
COPY studio/electron/workspace-recovery.ts studio/electron/company-sign-in-protocol.ts studio/electron/capture-messages.ts ./studio/electron/
COPY mnemion/service/recovery_kit.html ./mnemion/service/recovery_kit.html
COPY mnemion/product_telemetry/disclosure.json ./mnemion/product_telemetry/disclosure.json
COPY mnemion/assets ./mnemion/assets
COPY studio/branding/mnemion.svg studio/branding/assets.json studio/branding/verify.mjs ./studio/branding/
COPY assets/mnemion_logo.png ./assets/
COPY docs ./docs
COPY README.md SECURITY.md CONTRIBUTING.md ./
COPY studio/README.md ./studio/README.md
RUN npm --prefix studio/frontend run build
RUN apt-get update && apt-get install -y --no-install-recommends python3 \
    && rm -rf /var/lib/apt/lists/*
COPY LICENSE NOTICE deploy/notices.py ./
RUN python3 notices.py --root /build --frontend /build/studio/frontend --output /build/frontend-notices

FROM ghcr.io/astral-sh/uv:0.12.24@sha256:3af4716e991d6956a41e573eab705d0ee08500cd829ed30293eb8472f372c65a AS uv
FROM python:3.13-slim-trixie@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f AS runtime
COPY --from=uv /uv /usr/local/bin/uv
# pg_dump/pg_restore must match the supplied PostgreSQL 17 deployment.
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client-17 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 mnemion \
    && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /tmp/mnemion mnemion
WORKDIR /opt/mnemion
COPY pyproject.toml uv.lock README.md LICENSE NOTICE ./
COPY mnemion ./mnemion
COPY deploy/notices.py ./deploy/notices.py
COPY deploy/license-overrides ./deploy/license-overrides
RUN uv sync --locked --no-dev --no-editable --python /usr/local/bin/python --no-cache \
    && .venv/bin/python deploy/notices.py --root /opt/mnemion --python --output /opt/mnemion/licenses/python \
    && rm /usr/local/bin/uv
COPY --from=studio /build/studio/frontend/dist ./studio
COPY --from=studio /build/frontend-notices ./licenses/frontend
ENV PATH="/opt/mnemion/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    MNEMION_MODEL_CACHE=/models MNEMION_MODEL_THREADS=2 \
    MNEMION_DB_POOL_SIZE=10 MNEMION_HTTP_CONCURRENCY=64 \
    MNEMION_PG_BIN=/usr/lib/postgresql/17/bin
USER 10001:10001
EXPOSE 7892
ENTRYPOINT ["python", "-m", "mnemion.service.deployment"]
CMD ["api"]

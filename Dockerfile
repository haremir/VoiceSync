# ── Base image ────────────────────────────────────────────────────────────────
FROM python:3.11-slim

# ── System dependencies ────────────────────────────────────────────────────────
# ffmpeg is required by pydub for audio merging and MP3 export.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# ── uv package manager ─────────────────────────────────────────────────────────
# Copy the uv binary from the official image so we never need pip inside the container.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# ── Working directory ──────────────────────────────────────────────────────────
WORKDIR /app

# ── Dependency layer (cached unless pyproject.toml / uv.lock change) ──────────
# Copy only the lock files first so Docker can reuse this expensive layer
# on every rebuild that only touches application code.
COPY pyproject.toml uv.lock ./
COPY pkuseg_dummy/ ./pkuseg_dummy/

RUN uv sync --frozen --no-dev

# ── Application code ───────────────────────────────────────────────────────────
COPY main.py tts_engine.py config.py ./

# ── Runtime directories ────────────────────────────────────────────────────────
# Create voices/ and outputs/ so the container starts cleanly even without
# bind-mounts (e.g. during local docker run without compose).
RUN mkdir -p voices outputs

# ── Exposed port ───────────────────────────────────────────────────────────────
EXPOSE 8000

# ── Entrypoint ─────────────────────────────────────────────────────────────────
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

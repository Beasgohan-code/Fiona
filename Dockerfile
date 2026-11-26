# Single-container deployment: one bot client loads both feature sets.
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    MALLOC_ARENA_MAX=2 \
    SET_CMDS=False \
    EXTRA_PLUGINS=False \
    PYTHONPATH=/app/music:/app/waifu

# ffmpeg is required by voice-chat playback; git is used by a few retained
# maintenance helpers. No compiler toolchain is needed for the pinned wheels.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates ffmpeg git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first so source changes don't invalidate this layer.
COPY requirements.txt requirements.txt
COPY requirements/ requirements/
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

# Copy both feature packages and run them from the Music component directory,
# which is where its bundled assets and runtime paths are expected.
COPY . .
RUN groupadd --system --gid 10001 fiona \
    && useradd --system --uid 10001 --gid fiona --create-home --home-dir /home/fiona fiona \
    && mkdir -p /app/music/cache /app/music/downloads \
       /app/music/logs /app/music/tempdb \
    && chown -R fiona:fiona /app /home/fiona

WORKDIR /app/music
USER fiona

# launcher.py validates credentials then execs merged.py; the merged runner
# attaches both feature sets to the same client (never two polling bots).
CMD ["python", "/app/launcher.py"]

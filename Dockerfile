# Use the official uv image with Python 3.13 on Debian Bookworm Slim
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

# Enable bytecode compilation and use copy mode for linking
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install git (required by uv to fetch git-based dependencies like pyxelate)
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# Install dependencies using bind mounts for config files to avoid extra layers in the builder
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# Final runtime stage
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

# Install system dependencies needed for runtime (e.g. ffmpeg for yt-dlp/audio processing)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the virtual environment from the builder
COPY --from=builder /app/.venv /app/.venv

# Copy the rest of the application code
COPY . .

# Create the temp directory for downloading/converting files and ensure permissions
RUN mkdir -p temp && chmod 777 temp

# Place the virtual environment's bin on the PATH
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Run the Discord bot using python directly from the virtual environment
CMD ["python", "main.py"]


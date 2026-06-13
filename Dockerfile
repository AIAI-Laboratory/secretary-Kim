# Use a modern, official Python image with Debian Bookworm
FROM python:3.13-slim-bookworm

# Install system dependencies needed for general operations
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy uv executable from the official uv image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Enable bytecode compilation for faster startup and performance
ENV UV_COMPILE_BYTECODE=1
ENV PYTHONUNBUFFERED=1

# Copy dependency definition files
COPY pyproject.toml uv.lock ./

# Install python dependencies with caching, excluding dev dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev


# Copy the rest of the application code
COPY . .

# Create the temp directory for downloading/converting PDFs and ensure permissions
RUN mkdir -p temp && chmod 777 temp

# Run the Discord bot
CMD ["uv", "run", "main.py"]

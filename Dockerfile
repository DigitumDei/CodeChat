ARG baseImage=python:3.12-slim
# ---------- builder ----------
FROM ${baseImage} AS builder

# Use BuildKit cache mounts for apt and pip
RUN --mount=type=cache,target=/var/cache/apt \
    --mount=type=cache,target=/var/lib/apt \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential git python3-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /src

# Create venv
RUN python3 -m venv /usr/local
ENV PATH="/usr/local/bin:${PATH}"

# Install pip & Poetry
RUN --mount=type=cache,id=pipcache,target=/root/.cache/pip \
    pip install --no-cache-dir pip==25.0.1 poetry==2.1.2

# Set WORKDIR for poetry commands relative to the project root
WORKDIR /src/daemon

# Copy project definition and lock file FIRST for caching
COPY daemon/pyproject.toml daemon/poetry.lock ./

# Copy the rest of the source code needed for installation and tests
COPY daemon/codechat ./codechat
COPY daemon/tests ./tests 

# Install ALL dependencies (including dev) using Poetry
# This ensures pytest is available in the venv
RUN --mount=type=cache,id=pipcache,target=/root/.cache/pip \
    poetry install --no-interaction --no-ansi --with dev

RUN --mount=type=cache,id=pipcache,target=/root/.cache/pip \
    poetry build -f wheel -o /app/dist

RUN --mount=type=cache,id=pipcache,target=/root/.cache/pip \
    pip install /app/dist/*.whl


# The venv at /usr/local now contains the project and ALL dependencies (runtime + dev)

# ---------- test ----------
FROM builder AS test
# WORKDIR is inherited (/src/daemon)
# Source code and tests are already copied from the builder stage
# The venv with pytest is inherited from the builder stage
CMD ["poetry", "run", "pytest", "-q"]

# ---------- runtime ----------
FROM ${baseImage} AS prod

# Copy the entire populated venv from the builder
# This venv contains runtime *and* dev dependencies.
# For a smaller image, you could create a separate runtime venv in builder
# using `poetry install --no-dev`, but this approach is simpler.
COPY --from=builder /usr/local /usr/local

# Ensure the venv's bin directory is in the PATH
ENV PATH="/usr/local/bin:${PATH}"

# Copy tree-sitter libs if needed
COPY --from=builder /usr/local/lib/python*/site-packages/tree_sitter_languages/*.so \
        /usr/local/lib/

# Non-root user setup
RUN adduser --system --no-create-home --group codechat
USER codechat
WORKDIR /workspace
EXPOSE 16005

# Entrypoint uses the script installed into the venv's bin directory
ENTRYPOINT ["codechat", "start", "--host", "0.0.0.0", "--port", "16005"]


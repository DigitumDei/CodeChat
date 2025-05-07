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

WORKDIR /src/daemon
COPY daemon/pyproject.toml daemon/poetry.lock ./

COPY daemon/codechat ./codechat
COPY daemon/tests ./tests 

RUN --mount=type=cache,id=poetry-cache,target=/root/.cache/pypoetry \
    --mount=type=cache,id=pip-cache,target=/root/.cache/pip \
    poetry install --no-interaction --no-ansi --with dev

RUN --mount=type=cache,id=pipcache,target=/root/.cache/pip \
    poetry build -f wheel -o /app/dist

# ---------- test ----------
FROM builder AS test

CMD ["poetry", "run", "pytest", "-q"]

# ---------- runtime ----------
FROM ${baseImage} AS prod

COPY --from=builder /app/dist/ /app/dist/

# Ensure the venv's bin directory is in the PATH
ENV PATH="/usr/local/bin:${PATH}"

RUN --mount=type=cache,id=pipcache,target=/root/.cache/pip \
    pip install /app/dist/*.whl 

# Non-root user setup
RUN adduser --system --no-create-home --group codechat
USER codechat
WORKDIR /workspace
EXPOSE 16005

# Entrypoint uses the script installed into the venv's bin directory
ENTRYPOINT ["codechat", "start", "--host", "0.0.0.0", "--port", "16005"]


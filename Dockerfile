ARG baseImage=python:3.12-slim
# ---------- builder ----------
FROM ${baseImage} AS builder

ENV POETRY_VIRTUALENVS_CREATE=false \ 
    POETRY_VIRTUALENVS_IN_PROJECT=false
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
# 1. copy lock files and install deps
COPY daemon/pyproject.toml daemon/poetry.lock ./
RUN --mount=type=cache,id=pip-cache,target=/root/.cache/pip \
    poetry install --no-root --no-interaction --no-ansi --with dev
# 2. now bring in the source
COPY daemon/codechat ./codechat
COPY daemon/tests   ./tests

# 3. install the root package (quick)
RUN poetry install --only-root --no-interaction --no-ansi

RUN --mount=type=cache,id=poetry-cache,target=/root/.cache/pypoetry \
    --mount=type=cache,id=pip-cache,target=/root/.cache/pip \
    poetry install --no-interaction --no-ansi --with dev

RUN --mount=type=cache,id=pipcache,target=/root/.cache/pip \
    poetry build -f wheel -o /app/dist

# ---------- test ----------
FROM builder AS test

CMD ["poetry", "run", "pytest", "-q"]

# ---------- runtime ----------
FROM ${baseImage} AS prodsetup

ENV PATH="/usr/local/bin:${PATH}"

# Install git in the runtime stage as well
RUN --mount=type=cache,target=/var/cache/apt \
    --mount=type=cache,target=/var/lib/apt \
    apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

# Add /workspace to safe.directory system-wide for Git
RUN git config --system --add safe.directory /workspace

FROM prodsetup as prod

COPY --from=builder /app/dist/ /app/dist/
RUN --mount=type=cache,id=pipcache,target=/root/.cache/pip \
    pip install --no-cache-dir /app/dist/*.whl

RUN adduser --system --no-create-home --group codechat
USER codechat
WORKDIR /workspace
EXPOSE 16005

ENTRYPOINT ["codechat", "start", "--host", "0.0.0.0", "--port", "16005"]

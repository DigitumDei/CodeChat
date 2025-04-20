ARG baseImage=python:3.12-slim
# ---------- builder ----------
FROM ${baseImage} AS builder

# 1) Install build deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential git python3-dev && \
    # Clean up apt cache to reduce layer size
    rm -rf /var/lib/apt/lists/*

WORKDIR /src

# 2) Create a venv directly in /usr/local
RUN python3 -m venv /usr/local

# 3) Ensure the venv's bin is on PATH for subsequent RUN commands
ENV PATH="/usr/local/bin:${PATH}"

# 4) Install pip & Poetry into the venv
#    Using --no-cache-dir helps keep the layer smaller
RUN pip install --no-cache-dir pip==25.0.1 poetry==2.1.2

# 5) Copy your project and build your wheel
#    Copy only necessary files first for better caching
COPY daemon/pyproject.toml daemon/poetry.lock ./
COPY daemon ./daemon
#    Build the wheel inside the daemon directory
RUN cd daemon && poetry build -f wheel

# 6) Install your wheel + runtime deps into the same venv (/usr/local)
RUN pip install --no-cache-dir \
      daemon/dist/*.whl \
      faiss-cpu==1.8.* \
      tree-sitter==0.24.0 \
      tree_sitter_languages==1.10.2

# Now /usr/local contains the full venv with your app installed

# ---------- runtime ----------
FROM ${baseImage} AS runtime

# Copy the entire populated venv from the builder
COPY --from=builder /usr/local /usr/local

# Ensure the venv's bin directory is in the PATH for the runtime
ENV PATH="/usr/local/bin:${PATH}"

# tiny layer with Tree‑sitter shared libs (adjust path if needed)
# Note: tree_sitter_languages might install .so files elsewhere,
# check the builder stage if this copy fails.
COPY --from=builder /usr/local/lib/python*/site-packages/tree_sitter_languages/*.so \
        /usr/local/lib/

# non‑root for safety - consider --system for service accounts
RUN adduser --system --no-create-home --group codechat # Create group too
USER codechat
WORKDIR /workspace
EXPOSE 16005

# Entrypoint should now work as /usr/local/bin is in PATH
# and the shebang in /usr/local/bin/codechat points to /usr/local/bin/python3
ENTRYPOINT ["codechat", "start", "--host", "0.0.0.0", "--port", "16005"]

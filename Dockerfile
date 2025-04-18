ARG baseImage=python:3.12-slim
# ---------- builder ----------
FROM ${baseImage} AS builder

# 1) Install build deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential git python3-dev

WORKDIR /src

# 2) Create a venv in /install
RUN python3 -m venv /install

# 3) Ensure the venv's bin is on PATH
ENV PATH="/install/bin:${PATH}"

# 4) Install pip & Poetry into the venv
RUN pip install --no-cache-dir pip==25.0.1 poetry==2.1.2


# 5) Copy your project and build your wheel
COPY daemon/pyproject.toml daemon/poetry.lock ./
COPY daemon ./daemon
RUN cd daemon && poetry build -f wheel

# 6) Install your wheel + runtime deps into the same venv
RUN pip install --no-cache-dir \
      daemon/dist/*.whl \
      faiss-cpu==1.8.* \
      tree-sitter==0.24.0 \
      tree_sitter_languages==1.10.2

# Now /install contains:
#   /install/bin/{python,pip,poetry,codechat,…}
#   /install/lib/python3.12/site-packages/{poetry,…,your_packages}

# ---------- runtime ----------
FROM ${baseImage} AS runtime
COPY --from=builder /install /usr/local
# tiny layer with Tree‑sitter shared libs for 8 common languages
COPY --from=builder /usr/local/lib/python*/site-packages/tree_sitter_languages/*.so \
        /usr/local/lib/
# non‑root for safety
RUN adduser --disabled-password codechat
USER codechat
WORKDIR /workspace
EXPOSE 16005
ENTRYPOINT ["codechat", "serve", "--host", "0.0.0.0", "--port", "16005"]
    
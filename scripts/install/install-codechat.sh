#!/usr/bin/env bash
set -euo pipefail

# 1️⃣ Check we’re inside a Git repo
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "⚠️  Not inside a Git repository." >&2
  exit 1
fi

# 2️⃣ Create the .codechat folder
CONFIG_DIR=".codechat"
if [ -d "$CONFIG_DIR" ]; then
  echo "ℹ️  $CONFIG_DIR already exists."
else
  mkdir "$CONFIG_DIR"
  echo "✅ Created $CONFIG_DIR/"
fi

# 2.1️⃣ Ensure .codechat/ is in .gitignore
GITIGNORE=".gitignore"
ENTRY="$CONFIG_DIR/"
# create .gitignore if missing
if [ ! -f "$GITIGNORE" ]; then
  touch "$GITIGNORE"
  echo "✅ Created $GITIGNORE"
fi
# append ignore entry if not already present
if ! grep -Fxq "$ENTRY" "$GITIGNORE"; then
  {
    echo ""
    echo "# Ignore CodeChat config"
    echo "$ENTRY"
  } >> "$GITIGNORE"
  echo "✅ Added '$ENTRY' to $GITIGNORE"
else
  echo "ℹ️  '$ENTRY' already in $GITIGNORE"
fi

# 3️⃣ Set Docker image
IMAGE="codechat:latest"   # ← replace with your actual image name/tag
echo "ℹ️  Currently just using locally built image $IMAGE…"
# To pull from registry instead, uncomment:
# echo "⬇️  Pulling Docker image $IMAGE…"
# docker pull "$IMAGE"

# 4️⃣ Write a minimal docker-compose.yml
COMPOSE_PATH="$CONFIG_DIR/docker-compose.yml"
cat > "$COMPOSE_PATH" <<EOF
version: "3.8"
services:
  codechat:
    image: $IMAGE
    volumes:
      - type: bind
        source: ../
        target: /workspace
        read_only: true
      - type: bind
        source: ./
        target: /config
        read_only: false
    ports:
      - "16005:16005"
EOF
echo "✅ Generated $COMPOSE_PATH"

# 5️⃣ Create a helper script in .codechat
HELPER_PATH="$CONFIG_DIR/codechat.sh"
cat > "$HELPER_PATH" <<'EOF'
#!/usr/bin/env bash
docker-compose -f .codechat/docker-compose.yml up --build -d
EOF
chmod +x "$HELPER_PATH"
echo "✅ Added helper script at $HELPER_PATH"

echo
echo "🎉 All set! Run $HELPER_PATH to start CodeChat."

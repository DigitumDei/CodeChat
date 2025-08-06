# No Docker Desktop Setup - WSL Docker with Windows Docker CLI

## WSL Setup

```bash
# Update package repositories
sudo apt-get update

# Install required packages
sudo apt-get install ca-certificates curl

# Create directory for apt keyrings
sudo install -m 0755 -d /etc/apt/keyrings

# Download Docker's official GPG key
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc

# Make the key readable
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add Docker repository to apt sources
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Update package repositories again
sudo apt-get update

# Install Docker Engine and related packages
sudo apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Test Docker installation
sudo docker run hello-world

```

```bash
# Create Docker startup script
sudo tee /usr/local/bin/start-docker.sh <<'EOF'
#!/bin/sh
# Start dockerd listening on both sockets
nohup dockerd \
  -H unix:///var/run/docker.sock \
  -H tcp://0.0.0.0:2375 \
  --containerd=/run/containerd/containerd.sock \
> /var/log/docker-boot.log 2>&1 &
EOF

# Make the script executable
sudo chmod +x /usr/local/bin/start-docker.sh

# Configure WSL to auto-start Docker
sudo nano /etc/wsl.conf
# Add the following content:
[boot]
command = /usr/local/bin/start-docker.sh

# Close WSL and restart it from Windows to apply changes
# In Windows PowerShell: wsl --shutdown
# Then restart WSL
```

## Windows Setup

```powershell
# Set execution policy to allow script installation
Set-ExecutionPolicy Bypass -Scope Process -Force

# Install Chocolatey package manager
iwr https://community.chocolatey.org/install.ps1 -UseBasicParsing | iex

# Install Docker CLI and Docker Compose
choco install docker-cli -y
choco install docker-compose -y

curl -L "https://github.com/docker/buildx/releases/download/v0.26.1/buildx-v0.26.1.windows-amd64.exe" -o C:/ProgramData/Docker/cli-plugins/docker-buildx.exe

# Remove Docker Desktop credential helper configuration
# Edit or create config.json and remove "credsStore": "desktop" entry
notepad $env:USERPROFILE\.docker\config.json

# Configure PowerShell profile to set Docker host
notepad $PROFILE
# Add the following lines to the profile:
$Env:DOCKER_HOST = 'tcp://localhost:2375'
$Env:DOCKER_BUILDKIT = '1'
$Env:COMPOSE_CONVERT_WINDOWS_PATHS = '1'

# Note: If path conversion issues occur with relative paths in docker-compose.yml,
# modify the codechat.ps1 script to call WSL's docker compose instead:
# wsl docker compose -f .codechat/docker-compose.yml up --build -d
# This ensures proper Unix path handling by the WSL Docker daemon
```

## VS Code Setup

```bash
# Install Microsoft Container Tools extension in VS Code
# Extension ID: ms-azuretools.vscode-containers

# Create Docker context for WSL TCP connection
docker context create wsl-tcp --docker "host=tcp://localhost:2375"

# In VS Code Containers window:
# - Use the Docker Contexts dropdown in the Containers panel
# - Select "wsl-tcp" from the list as the active Docker context
# - This allows the Containers panel to connect properly instead of using named pipes
```
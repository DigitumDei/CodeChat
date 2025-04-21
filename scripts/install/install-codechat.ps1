# install-codechat.ps1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# 1 Check we’re inside a Git repo
try {
    git rev-parse --is-inside-work-tree 2>$null | Out-Null
} catch {
    Write-Error "⚠️ Not inside a Git repository."
    exit 1
}

# 2 Create the .codechat folder
$configDir = ".codechat"
if (-not (Test-Path $configDir)) {
    New-Item -ItemType Directory -Path $configDir | Out-Null
    Write-Host "✅ Created $configDir/"
} else {
    Write-Host "ℹ️  $configDir already exists."
}

# 2.1 Ensure .codechat/ is in .gitignore
$gitignore = ".gitignore"
$entry     = "$configDir/"
if (-not (Test-Path $gitignore)) {
    New-Item -ItemType File -Path $gitignore | Out-Null
    Write-Host "✅ Created $gitignore"
}
$content = Get-Content $gitignore -ErrorAction SilentlyContinue
if ($content -notcontains $entry) {
    Add-Content $gitignore ""
    Add-Content $gitignore "# Ignore CodeChat config"
    Add-Content $gitignore $entry
    Write-Host "✅ Added '$entry' to $gitignore"
} else {
    Write-Host "ℹ️  '$entry' already in $gitignore"
}

# 3 Pull the Docker image
$image = "codechat:latest"   # ← replace with your actual image name/tag
Write-Host "ℹ️ Currently just using locally built image $image…"
# Write-Host "⬇️  Pulling Docker image $image…"
# docker pull $image

# 4 Write a minimal docker-compose.yml
$composePath = "$configDir/docker-compose.yml"
@"
version: "3.8"
services:
  codechat:
    image: $image
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
"@ | Set-Content -Path $composePath
Write-Host "✅ Generated $composePath"

# 5 Create a helper in .codechat
$helperPath = "$configDir\codechat.ps1"
if (-not (Test-Path $configDir)) {
    New-Item -ItemType Directory -Path $configDir | Out-Null
}
@"
docker-compose -f .codechat/docker-compose.yml up --build -d
"@ | Set-Content -Path $helperPath
Write-Host "✅ Added helper script at $helperPath"

Write-Host "`n🎉 All set! Run $helperPath to start CodeChat."

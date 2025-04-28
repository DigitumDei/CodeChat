# Local Build

## Build the daemon Dockerfile

``` shell   
docker build -t codechat:latest .
```

## Install codechat in target repo
Run the installation script which will create the required folder and docker compose.

``` shell
# windows
<path to codechat repo>/scripts/install/install-codechat.ps1

#linux/mac
<path to codechat repo>/scripts/install/install-codechat.sh
```

## Launch codechat

In the target repo root folder

``` shell
# windows
.\.codechat\codechat.ps1 

#linux/mac
./.codechat/codechat.sh
```
# Official Build
TODO
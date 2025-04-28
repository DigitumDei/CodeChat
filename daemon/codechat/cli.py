import json
import os
import click
import requests
from codechat.server import serve
import structlog
logger = structlog.get_logger(__name__)

@click.group()
def main():
    """CodeChat Daemon CLI"""
    pass

@main.command()
@click.option('--host', default='127.0.0.1', help='Host to bind the server to')
@click.option('--port', default=16005, type=int, help='Port to listen on')
def start(host: str, port: int):
    """Start the CodeChat daemon server"""
    serve(host, port)

@main.group()
def config():
    """Get or set CodeChat config."""
    pass

@config.command()
@click.argument("key")
@click.argument("value")
def set(key: str, value: str):
    """Set CODECHAT config key"""
    cfg_path = os.path.expanduser("/config/config.json")
    os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
    cfg = {}
    if os.path.exists(cfg_path):
        click.echo(f"opening {cfg_path}.")
        with open(cfg_path, "r") as f:
            cfg = json.load(f)
    cfg[key] = value
    with open(cfg_path, "w") as f:
        click.echo(f"writing {cfg_path}.")
        json.dump(cfg, f, indent=2)
    click.echo(f"Set {key}.")
    try:
        server_url = "http://localhost:16005/admin/reload-config"
        response = requests.post(server_url, timeout=5) # Add a timeout
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        logger.info("Successfully signaled server to reload configuration.")
    except requests.exceptions.RequestException as e:
        logger.info(f"Warning: Could not signal the running server to reload config: {e}")
        logger.info("The configuration file was updated, but you may need to restart the server manually.")


if __name__ == '__main__':
    main()
import json
import os
import click
from codechat.server import serve

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
        with open(cfg_path, "r") as f:
            cfg = json.load(f)
    cfg[key] = value
    with open(cfg_path, "w") as f:
        json.dump(cfg, f, indent=2)
    click.echo(f"Set {key}.")

if __name__ == '__main__':
    main()
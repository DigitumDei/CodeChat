import click
from codechat.server import serve

@click.group()
def main():
    """CodeChat Daemon CLI"""
    pass

@main.command()
@click.option('--host', default='127.0.0.1', help='Host to bind the server to')
@click.option('--port', default=5005, type=int, help='Port to listen on')
def start(host: str, port: int):
    """Start the CodeChat daemon server"""
    serve(host, port)

if __name__ == '__main__':
    main()
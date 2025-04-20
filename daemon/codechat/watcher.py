import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from codechat.indexer import Indexer

class Watcher(FileSystemEventHandler):
    """Watches filesystem changes and triggers re-indexing"""
    def __init__(self, indexer: Indexer, path: str = '.'):
        self.indexer = indexer
        self.observer = Observer()
        self.path = path

    def start(self):
        self.observer.schedule(self, self.path, recursive=True)
        self.observer_thread = threading.Thread(target=self.observer.start, daemon=True)
        self.observer_thread.start()

    def on_modified(self, event):
        # trigger re-index
        self.indexer.build_index()
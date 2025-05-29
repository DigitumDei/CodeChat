import threading
import structlog
from watchdog.observers.polling import PollingObserver as Observer # Use PollingObserver
from watchdog.events import FileSystemEventHandler

from codechat.indexer import Indexer

logger = structlog.get_logger(__name__)

class Watcher(FileSystemEventHandler):
    """Watches filesystem changes and triggers re-indexing"""
    def __init__(self, indexer: Indexer, path: str = '/workspace'):
        super().__init__()
        self.indexer = indexer
        self.observer = Observer()
        self.path = path
        logger.info("Watcher: Observer instance created", observer_id=id(self.observer), observer_actual_type=type(self.observer).__name__)
    def _run_observer(self):
        try:
            # self.observer.start() is a blocking call that runs the observer loop
            self.observer.start()
        except Exception:
            logger.error("Observer thread: Crashed unexpectedly.", path=self.path, exc_info=True)
        finally:
            logger.info("Observer thread: Exited.", path=self.path)

    def start(self):
        self.observer.schedule(self, self.path, recursive=True)
        self.observer_thread = threading.Thread(target=self._run_observer, daemon=True)
        self.observer_thread.start()
        logger.info("Watcher: Observer thread started.", path=self.path)

    def on_any_event(self, event):
        event_details = {
            "event_type": event.event_type,
            "src_path": event.src_path,
            "is_directory": event.is_directory,
        }
        if hasattr(event, 'dest_path'): # For moved events
            event_details["dest_path"] = event.dest_path
        logger.info("Watcher: on_any_event received", **event_details)

    def on_modified(self, event):
        logger.info("Watcher: on_modified triggered, forwarding to Indexer", src_path=event.src_path, is_directory=event.is_directory)
        self.indexer.process_file_event(event_type="modified", src_path_str=event.src_path)

    def on_created(self, event):
        logger.info("Watcher: on_created triggered, forwarding to Indexer", src_path=event.src_path, is_directory=event.is_directory)
        self.indexer.process_file_event(event_type="created", src_path_str=event.src_path)

    def on_deleted(self, event):
        logger.info("Watcher: on_deleted triggered, forwarding to Indexer", src_path=event.src_path, is_directory=event.is_directory)
        self.indexer.process_file_event(event_type="deleted", src_path_str=event.src_path)

    def on_moved(self, event):
        logger.info("Watcher: on_moved triggered, forwarding to Indexer", src_path=event.src_path, dest_path=event.dest_path, is_directory=event.is_directory)
        self.indexer.process_file_event(event_type="moved", src_path_str=event.src_path, dest_path_str=event.dest_path)
         
        
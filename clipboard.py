import json, threading
from watchdog.events import FileSystemEventHandler, FileModifiedEvent
from watchdog.observers import Observer
import pyperclip

CACHE_FILE = "./clipboard_stack.json"

class ClipboardStack:
    """A persistent clipboard stack backed by a JSON cache file with live reload."""

    def __init__(self, path: Path = CACHE_FILE) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._load()
        self._start_watcher()

    def _load(self) -> None:
        """Read stack from cache file, initialising empty if missing or malformed."""
        try:
            self._items: list[str] = json.loads(self._path.read_text())
            if not isinstance(self._items, list):
                raise ValueError
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            self._items = []

    def _save(self) -> None:
        """Write current stack to cache file."""
        self._path.write_text(json.dumps(self._items, indent=2))

    def _start_watcher(self) -> None:
        """Start a background watchdog observer on the cache file."""
        handler = _ReloadHandler(self)
        self._observer = Observer()
        self._observer.schedule(handler, str(self._path.parent), recursive=False)
        self._observer.daemon = True
        self._observer.start()

    def push(self, text: str) -> None:
        """Append text to the stack."""
        with self._lock:
            self._items.append(text)
            self._save()

    def pop(self, index: int = -1) -> str:
        """Remove and return the item at index, defaulting to the last."""
        with self._lock:
            item = self._items.pop(index)
            self._save()
        return item

    def get(self, index: int = -1) -> str:
        """Return the item at index without removing it, defaulting to the last."""
        with self._lock:
            return self._items[index]

    def peek(self, index: int = -1) -> str:
        """Copy the item at index to the system clipboard as plain text and return it."""
        with self._lock:
            item = self._items[index]
        pyperclip.copy(item)
        return item

    def list(self) -> list[str]:
        """Return a shallow copy of current items."""
        with self._lock:
            return self._items.copy()

    def stop(self) -> None:
        """Stop the file watcher. Call on shutdown if not using daemon mode."""
        self._observer.stop()
        self._observer.join()

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def __repr__(self) -> str:
        with self._lock:
            return f"ClipboardStack({self._items!r})"


class _ReloadHandler(FileSystemEventHandler):
    """Triggers a stack reload when the cache file is modified externally."""

    def __init__(self, stack: ClipboardStack) -> None:
        self._stack = stack

    def on_modified(self, event: FileModifiedEvent) -> None:
        if Path(event.src_path) == self._stack._path:
            with self._stack._lock:
                self._stack._load()
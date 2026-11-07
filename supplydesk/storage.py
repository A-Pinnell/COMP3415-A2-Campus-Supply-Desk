"""JSON storage used by the local order desk."""

import json
import os
import tempfile
from pathlib import Path


class JsonStore:
    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        if self.path.exists():
            with self.path.open(encoding="utf-8") as stream:
                return json.load(stream)
        catalog_path = Path(__file__).with_name("catalog.json")
        with catalog_path.open(encoding="utf-8") as stream:
            catalog = json.load(stream)
        return {
            "schema_version": 1,
            "next_order_number": 1,
            "catalog": catalog,
            "orders": [],
        }

    def save(self, state):
        """Atomically replace the state file after a complete JSON write."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary_path = Path(stream.name)
                json.dump(state, stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, self.path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

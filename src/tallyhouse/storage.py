"""Content-addressed storage for raw robots.txt evidence.

Bodies are keyed by sha256 and shared across all periods, so the large
majority of files that do not change between weeks cost nothing to retain.
"""

import gzip
import hashlib
import json
from pathlib import Path


def body_path(root: Path, sha: str) -> Path:
    return root / "raw" / "bodies" / sha[:2] / f"{sha}.txt.gz"


def store_body(root: Path, data: bytes) -> str:
    """Store a body and return its sha256. Idempotent."""
    sha = hashlib.sha256(data).hexdigest()
    path = body_path(root, sha)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        # mtime=0 keeps the gzip output byte-identical across runs.
        with path.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as handle:
                handle.write(data)
    return sha


def load_body(root: Path, sha: str) -> bytes:
    with gzip.open(body_path(root, sha), "rb") as handle:
        return handle.read()


def manifest_path(root: Path, period: str) -> Path:
    return root / "raw" / period / "manifest.json"


def write_manifest(root: Path, period: str, records: list[dict]) -> Path:
    path = manifest_path(root, period)
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(records, key=lambda r: r["domain"])
    path.write_text(json.dumps(ordered, indent=2, sort_keys=True) + "\n")
    return path


def read_manifest(root: Path, period: str) -> list[dict]:
    return json.loads(manifest_path(root, period).read_text())

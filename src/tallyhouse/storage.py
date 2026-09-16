"""Content-addressed storage for raw robots.txt evidence.

Bodies are keyed by sha256 and shared across all periods, so the large
majority of files that do not change between weeks cost nothing to retain.
"""

import gzip
import hashlib
import json
import os
from pathlib import Path


def body_path(root: Path, sha: str) -> Path:
    return root / "raw" / "bodies" / sha[:2] / f"{sha}.txt.gz"


def store_body(root: Path, data: bytes) -> str:
    """Store a body and return its sha256. Idempotent."""
    sha = hashlib.sha256(data).hexdigest()
    path = body_path(root, sha)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write to temp file, then atomically rename to final path.
        # This ensures we never leave a corrupt or partial body on disk.
        tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
        try:
            with tmp.open("wb") as raw:
                # mtime=0 and filename="" keep gzip output byte-identical across runs.
                with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as handle:
                    handle.write(data)
            os.replace(tmp, path)
        finally:
            # Clean up temp file if write failed.
            if tmp.exists():
                tmp.unlink()
    return sha


def load_body(root: Path, sha: str) -> bytes:
    with gzip.open(body_path(root, sha), "rb") as handle:
        return handle.read()


def manifest_path(root: Path, period: str) -> Path:
    return root / "raw" / period / "manifest.json"


def write_manifest(
    root: Path, period: str, records: list[dict], *, collector_version: str
) -> Path:
    """Write a period's manifest: the observations plus their provenance.

    collector_version is stamped here, at collection time, rather than computed
    later at print time. Evidence gathered at commit A and printed at commit B
    is evidence from A, and the field exists to say so. It is required rather
    than optional because a provenance field that can be omitted is a provenance
    field that will be.
    """
    path = manifest_path(root, period)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "collector_version": collector_version,
        "period": period,
        "observations": sorted(records, key=lambda r: r["domain"]),
    }
    # Write to temp file, then atomically rename to final path.
    # This ensures we never leave invalid JSON on disk.
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    try:
        tmp.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
        os.replace(tmp, path)
    finally:
        # Clean up temp file if write failed.
        if tmp.exists():
            tmp.unlink()
    return path


def read_manifest(root: Path, period: str) -> list[dict]:
    return _load_manifest(root, period)["observations"]


def manifest_collector_version(root: Path, period: str) -> str:
    """The commit of the collector that produced this period's evidence."""
    version = _load_manifest(root, period).get("collector_version")
    if not version:
        raise ValueError(
            f"manifest for {period} records no collector_version; the evidence "
            f"is unattributable and cannot be printed. Re-collect the period."
        )
    return version


def _load_manifest(root: Path, period: str) -> dict:
    return json.loads(manifest_path(root, period).read_text())

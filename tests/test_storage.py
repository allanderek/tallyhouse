import gzip

from tallyhouse.storage import (
    body_path,
    load_body,
    read_manifest,
    store_body,
    write_manifest,
)


def test_store_body_returns_sha256_and_roundtrips(tmp_path):
    sha = store_body(tmp_path, b"User-agent: *\nDisallow:\n")
    assert len(sha) == 64
    assert load_body(tmp_path, sha) == b"User-agent: *\nDisallow:\n"


def test_identical_bodies_deduplicate_to_one_file(tmp_path):
    a = store_body(tmp_path, b"same")
    b = store_body(tmp_path, b"same")
    assert a == b
    assert len(list(tmp_path.rglob("*.txt.gz"))) == 1


def test_bodies_are_stored_gzipped(tmp_path):
    sha = store_body(tmp_path, b"hello robots")
    with gzip.open(body_path(tmp_path, sha), "rb") as handle:
        assert handle.read() == b"hello robots"


def test_bodies_are_sharded_by_sha_prefix(tmp_path):
    sha = store_body(tmp_path, b"shard me")
    assert body_path(tmp_path, sha).parent.name == sha[:2]


def test_manifest_roundtrips(tmp_path):
    records = [{"domain": "example.com", "outcome": "Fetched", "sha256": "abc"}]
    write_manifest(tmp_path, "2026-09-14", records)
    assert read_manifest(tmp_path, "2026-09-14") == records


def test_manifest_is_sorted_by_domain_for_stable_diffs(tmp_path):
    write_manifest(
        tmp_path,
        "2026-09-14",
        [{"domain": "zzz.com"}, {"domain": "aaa.com"}],
    )
    assert [r["domain"] for r in read_manifest(tmp_path, "2026-09-14")] == [
        "aaa.com",
        "zzz.com",
    ]

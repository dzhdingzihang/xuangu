from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from scripts import publish_data_assets


class RecordingBackend(publish_data_assets.FilesystemBackend):
    def __init__(self, root: pathlib.Path, *, corrupt_key: str | None = None):
        super().__init__(root)
        self.puts: list[str] = []
        self.corrupt_key = corrupt_key

    def put(self, key: str, source: pathlib.Path) -> None:
        self.puts.append(key)
        super().put(key, source)

    def get(self, key: str) -> bytes | None:
        payload = super().get(key)
        if payload is not None and key == self.corrupt_key:
            return payload + b"corrupt"
        return payload


def fixture(root: pathlib.Path) -> dict:
    assets: dict[str, dict] = {}
    for name in publish_data_assets.REQUIRED_ASSET_NAMES:
        payload = json.dumps({"kind": name}, sort_keys=True, separators=(",", ":")).encode()
        digest = publish_data_assets.sha256_bytes(payload)
        prefix = "live-index" if name == "live_index" else name
        key = f"{prefix}/{digest}.json"
        path = root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        assets[name] = {"key": key, "sha256": digest, "byte_size": len(payload)}
    detail_payload = b'{"candidate":"A"}'
    detail_digest = publish_data_assets.sha256_bytes(detail_payload)
    detail_key = f"candidate-details/{detail_digest}.json"
    (root / detail_key).parent.mkdir(parents=True, exist_ok=True)
    (root / detail_key).write_bytes(detail_payload)
    assets["candidate_details"] = {
        "cand_fixture": {"sha256": detail_digest, "byte_size": len(detail_payload)}
    }
    manifest = {
        "contract_version": publish_data_assets.CONTRACT_VERSION,
        "snapshot_key": "snapshot.json",
        "generated_at": "2026-08-29T01:00:00+08:00",
        "snapshot_sha256": "a" * 64,
        "snapshot_byte_size": 123,
        **{f"{name}_key": assets[name]["key"] for name in publish_data_assets.REQUIRED_ASSET_NAMES},
        "candidate_detail_keys": {"cand_fixture": detail_key},
        "assets": assets,
    }
    (root / publish_data_assets.LATEST_MANIFEST_KEY).write_bytes(
        publish_data_assets.stable_json_bytes(manifest)
    )
    return manifest


class PublishDataAssetsTests(unittest.TestCase):
    def test_publication_slo_measures_checkpoint_to_publication_and_initializes_unknown(self) -> None:
        manifest = {
            "generated_at": "2026-08-29T01:30:00+00:00",
            "scheduler_health": {
                "scheduler_readiness": "READY",
                "generation_delay_seconds": 1800,
                "publication_slo_seconds": 2700,
            },
        }
        ready = publish_data_assets.publication_manifest(
            manifest,
            published_at="2026-08-29T01:50:00+00:00",
        )
        self.assertEqual(ready["scheduler_health"]["publication_delay_seconds"], 1200)
        self.assertEqual(
            ready["scheduler_health"]["checkpoint_publication_delay_seconds"], 3000
        )
        self.assertFalse(ready["scheduler_health"]["publication_within_slo"])

        initializing = publish_data_assets.publication_manifest(
            {
                **manifest,
                "scheduler_health": {
                    **manifest["scheduler_health"],
                    "scheduler_readiness": "INITIALIZING",
                },
            },
            published_at="2026-08-29T01:50:00+00:00",
        )
        self.assertIsNone(initializing["scheduler_health"]["publication_within_slo"])

    def test_manual_publication_without_checkpoint_fails_closed_for_slo(self) -> None:
        published = publish_data_assets.publication_manifest(
            {
                "generated_at": "2026-09-02T09:53:37+00:00",
                "scheduler_health": {
                    "scheduler_readiness": "DEGRADED",
                    "generation_delay_seconds": None,
                    "publication_slo_seconds": 2700,
                },
            },
            published_at="2026-09-02T09:56:46+00:00",
        )

        self.assertIsNone(
            published["scheduler_health"]["checkpoint_publication_delay_seconds"]
        )
        self.assertIs(
            published["scheduler_health"]["publication_within_slo"],
            False,
        )

    def test_immutable_objects_are_verified_before_alias_switch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = pathlib.Path(temporary)
            source = base / "source"
            remote = base / "remote"
            source.mkdir()
            fixture(source)
            backend = RecordingBackend(remote)

            published = publish_data_assets.publish(
                source,
                backend,
                published_at="2026-08-29T00:00:00+00:00",
            )

            self.assertEqual(backend.puts[-1], publish_data_assets.LATEST_MANIFEST_KEY)
            self.assertTrue(all(key != publish_data_assets.LATEST_MANIFEST_KEY for key in backend.puts[:-1]))
            self.assertEqual(published["contract_version"], "data-manifest-v1")
            self.assertEqual(published["publication_mode"], "r2-immutable-manifest-v1")
            self.assertEqual(
                json.loads((remote / publish_data_assets.LATEST_MANIFEST_KEY).read_text()),
                published,
            )

    def test_failed_immutable_verification_leaves_previous_manifest_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = pathlib.Path(temporary)
            source = base / "source"
            remote = base / "remote"
            source.mkdir()
            remote.mkdir()
            manifest = fixture(source)
            previous = b'{"snapshot_key":"previous.json"}'
            (remote / publish_data_assets.LATEST_MANIFEST_KEY).write_bytes(previous)
            backend = RecordingBackend(remote, corrupt_key=manifest["summary_key"])

            with self.assertRaises(publish_data_assets.PublicationError):
                publish_data_assets.publish(source, backend)

            self.assertEqual((remote / publish_data_assets.LATEST_MANIFEST_KEY).read_bytes(), previous)
            self.assertNotIn(publish_data_assets.LATEST_MANIFEST_KEY, backend.puts)

    def test_local_digest_mismatch_fails_before_any_upload(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = pathlib.Path(temporary)
            source = base / "source"
            remote = base / "remote"
            source.mkdir()
            manifest = fixture(source)
            (source / manifest["events_key"]).write_bytes(b"changed")
            backend = RecordingBackend(remote)

            with self.assertRaisesRegex(publish_data_assets.PublicationError, "mismatch"):
                publish_data_assets.publish(source, backend)

            self.assertEqual(backend.puts, [])

    def test_candidate_detail_key_must_be_content_addressed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = pathlib.Path(temporary)
            manifest = fixture(source)
            manifest["candidate_detail_keys"]["cand_fixture"] = "candidate-details/not-the-digest.json"
            (source / publish_data_assets.LATEST_MANIFEST_KEY).write_bytes(
                publish_data_assets.stable_json_bytes(manifest)
            )
            with self.assertRaisesRegex(publish_data_assets.PublicationError, "content-addressed"):
                publish_data_assets.validate_manifest(manifest, source)


if __name__ == "__main__":
    unittest.main()

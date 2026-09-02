#!/usr/bin/env python3
"""Publish one immutable data generation before switching the R2 alias.

The publisher deliberately has no Cloudflare API implementation of its own.
Production uses the pinned local Wrangler dependency and a narrowly scoped
Cloudflare token; tests use the filesystem backend.  Every immutable object is
read back and verified before ``latest-manifest.json`` is replaced.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Protocol


CONTRACT_VERSION = "data-manifest-v1"
LATEST_MANIFEST_KEY = "latest-manifest.json"
REQUIRED_ASSET_NAMES = (
    "runtime", "live_index", "summary", "candidates", "events", "history",
)


class PublicationError(ValueError):
    pass


class ObjectBackend(Protocol):
    def put(self, key: str, source: pathlib.Path) -> None: ...

    def get(self, key: str) -> bytes | None: ...


def stable_json_bytes(payload: dict) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def safe_object_key(value: object) -> str:
    key = str(value or "")
    pure = pathlib.PurePosixPath(key)
    if (
        not key
        or pure.is_absolute()
        or ".." in pure.parts
        or "\\" in key
        or key.startswith(".")
        or not key.endswith(".json")
    ):
        raise PublicationError(f"unsafe object key: {key!r}")
    return key


def _asset_descriptor(manifest: dict, name: str) -> dict:
    descriptor = (manifest.get("assets") or {}).get(name)
    expected_key = manifest.get(f"{name}_key")
    if not isinstance(descriptor, dict) or descriptor.get("key") != expected_key:
        raise PublicationError(f"manifest {name} descriptor/key mismatch")
    key = safe_object_key(descriptor.get("key"))
    digest = str(descriptor.get("sha256") or "")
    byte_size = descriptor.get("byte_size")
    expected_prefix = "live-index" if name == "live_index" else name
    if not key.startswith(f"{expected_prefix}/"):
        raise PublicationError(f"manifest {name} key has wrong prefix")
    if not digest or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise PublicationError(f"manifest {name} sha256 is invalid")
    if pathlib.PurePosixPath(key).stem != digest:
        raise PublicationError(f"manifest {name} is not content-addressed")
    if not isinstance(byte_size, int) or isinstance(byte_size, bool) or byte_size <= 0:
        raise PublicationError(f"manifest {name} byte_size is invalid")
    return {"key": key, "sha256": digest, "byte_size": byte_size}


def validate_manifest(manifest: dict, source_root: pathlib.Path) -> list[dict]:
    if not isinstance(manifest, dict) or manifest.get("contract_version") != CONTRACT_VERSION:
        raise PublicationError("data manifest contract_version is invalid")
    snapshot_key = safe_object_key(manifest.get("snapshot_key"))
    if "/" in snapshot_key:
        raise PublicationError("snapshot_key must be a filename")
    source_digest = str(manifest.get("snapshot_sha256") or "")
    if len(source_digest) != 64:
        raise PublicationError("snapshot_sha256 is invalid")
    if not isinstance(manifest.get("snapshot_byte_size"), int):
        raise PublicationError("snapshot_byte_size is invalid")

    descriptors = [_asset_descriptor(manifest, name) for name in REQUIRED_ASSET_NAMES]
    detail_keys = manifest.get("candidate_detail_keys") or {}
    detail_meta = ((manifest.get("assets") or {}).get("candidate_details") or {})
    if not isinstance(detail_keys, dict) or not isinstance(detail_meta, dict):
        raise PublicationError("candidate detail manifest fields are invalid")
    if set(detail_keys) != set(detail_meta):
        raise PublicationError("candidate detail keys and metadata do not match")
    for candidate_id, key_value in sorted(detail_keys.items()):
        if not str(candidate_id).startswith("cand_"):
            raise PublicationError(f"candidate detail id is invalid: {candidate_id!r}")
        key = safe_object_key(key_value)
        meta = detail_meta[candidate_id]
        if not key.startswith("candidate-details/") or not isinstance(meta, dict):
            raise PublicationError(f"candidate detail descriptor is invalid: {candidate_id}")
        digest = str(meta.get("sha256") or "")
        byte_size = meta.get("byte_size")
        if pathlib.PurePosixPath(key).stem != digest or len(digest) != 64:
            raise PublicationError(f"candidate detail is not content-addressed: {candidate_id}")
        if not isinstance(byte_size, int) or isinstance(byte_size, bool) or byte_size <= 0:
            raise PublicationError(f"candidate detail byte_size is invalid: {candidate_id}")
        descriptors.append({"key": key, "sha256": digest, "byte_size": byte_size})

    seen: set[str] = set()
    for descriptor in descriptors:
        key = descriptor["key"]
        if key in seen:
            raise PublicationError(f"duplicate immutable object key: {key}")
        seen.add(key)
        path = source_root / pathlib.PurePosixPath(key)
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise PublicationError(f"immutable object is missing: {key}") from exc
        if len(payload) != descriptor["byte_size"]:
            raise PublicationError(f"immutable object byte size mismatch: {key}")
        if sha256_bytes(payload) != descriptor["sha256"]:
            raise PublicationError(f"immutable object digest mismatch: {key}")
    return descriptors


@dataclass
class FilesystemBackend:
    root: pathlib.Path

    def put(self, key: str, source: pathlib.Path) -> None:
        target = self.root / pathlib.PurePosixPath(safe_object_key(key))
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.tmp")
        shutil.copyfile(source, temporary)
        os.replace(temporary, target)

    def get(self, key: str) -> bytes | None:
        path = self.root / pathlib.PurePosixPath(safe_object_key(key))
        try:
            return path.read_bytes()
        except FileNotFoundError:
            return None


@dataclass
class WranglerR2Backend:
    bucket: str
    command: tuple[str, ...]
    cwd: pathlib.Path

    def _run(self, *arguments: str) -> None:
        subprocess.run(
            [*self.command, "r2", "object", *arguments, "--remote"],
            cwd=self.cwd,
            check=True,
        )

    def put(self, key: str, source: pathlib.Path) -> None:
        self._run("put", f"{self.bucket}/{safe_object_key(key)}", "--file", str(source))

    def get(self, key: str) -> bytes | None:
        with tempfile.TemporaryDirectory(prefix="xuangu-r2-verify-") as temporary:
            target = pathlib.Path(temporary) / "object.json"
            try:
                self._run("get", f"{self.bucket}/{safe_object_key(key)}", "--file", str(target))
            except subprocess.CalledProcessError:
                return None
            return target.read_bytes() if target.is_file() else None


def publication_manifest(manifest: dict, published_at: str | None = None) -> dict:
    result = dict(manifest)
    result.pop("manifest_sha256", None)
    result["published_at"] = published_at or dt.datetime.now(dt.timezone.utc).isoformat(
        timespec="seconds"
    )
    result["publication_mode"] = "r2-immutable-manifest-v1"
    health = dict(result.get("scheduler_health") or {})
    try:
        generated = dt.datetime.fromisoformat(str(result.get("generated_at") or ""))
        published = dt.datetime.fromisoformat(str(result["published_at"]).replace("Z", "+00:00"))
        publication_delay = max(0, int((published - generated).total_seconds()))
    except (TypeError, ValueError):
        publication_delay = None
    generation_delay = health.get("generation_delay_seconds")
    checkpoint_publication_delay = (
        generation_delay + publication_delay
        if isinstance(generation_delay, int)
        and not isinstance(generation_delay, bool)
        and isinstance(publication_delay, int)
        else None
    )
    health.update(
        {
            "publication_delay_seconds": publication_delay,
            "checkpoint_publication_delay_seconds": checkpoint_publication_delay,
            "publication_slo_seconds": int(health.get("publication_slo_seconds") or 45 * 60),
            "publication_within_slo": (
                None
                if health.get("scheduler_readiness") == "INITIALIZING"
                else (
                    checkpoint_publication_delay
                    <= int(health.get("publication_slo_seconds") or 45 * 60)
                    if isinstance(checkpoint_publication_delay, int)
                    else False
                )
            ),
            "published_at": result["published_at"],
        }
    )
    result["scheduler_health"] = health
    result["manifest_sha256"] = sha256_bytes(stable_json_bytes(result))
    return result


def publish(
    source_root: pathlib.Path,
    backend: ObjectBackend,
    *,
    published_at: str | None = None,
) -> dict:
    manifest_path = source_root / LATEST_MANIFEST_KEY
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PublicationError("latest-manifest.json is unavailable or invalid") from exc
    descriptors = validate_manifest(manifest, source_root)

    # Preserve the alias for rollback if the final read-back unexpectedly
    # differs.  Until the alias put, no reader can observe the new generation.
    previous_manifest = backend.get(LATEST_MANIFEST_KEY)
    for descriptor in descriptors:
        key = descriptor["key"]
        source = source_root / pathlib.PurePosixPath(key)
        backend.put(key, source)
        remote = backend.get(key)
        if remote is None or len(remote) != descriptor["byte_size"]:
            raise PublicationError(f"published object byte size mismatch: {key}")
        if sha256_bytes(remote) != descriptor["sha256"]:
            raise PublicationError(f"published object digest mismatch: {key}")

    published = publication_manifest(manifest, published_at)
    with tempfile.TemporaryDirectory(prefix="xuangu-manifest-") as temporary:
        prepared = pathlib.Path(temporary) / LATEST_MANIFEST_KEY
        prepared.write_bytes(stable_json_bytes(published))
        backend.put(LATEST_MANIFEST_KEY, prepared)
        current = backend.get(LATEST_MANIFEST_KEY)
        if current != prepared.read_bytes():
            if previous_manifest is not None:
                rollback = pathlib.Path(temporary) / "previous-manifest.json"
                rollback.write_bytes(previous_manifest)
                backend.put(LATEST_MANIFEST_KEY, rollback)
            raise PublicationError("latest manifest verification failed")
    return published


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=pathlib.Path, default=pathlib.Path("public/data"))
    parser.add_argument("--bucket", default="xuangu-data")
    parser.add_argument("--filesystem-root", type=pathlib.Path)
    parser.add_argument("--wrangler-command", default="npx --no-install wrangler")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_root = args.source_root.resolve()
    manifest = json.loads((source_root / LATEST_MANIFEST_KEY).read_text(encoding="utf-8"))
    descriptors = validate_manifest(manifest, source_root)
    if args.dry_run:
        print(json.dumps({"validated": len(descriptors), "snapshot_key": manifest["snapshot_key"]}))
        return 0
    if args.filesystem_root:
        backend: ObjectBackend = FilesystemBackend(args.filesystem_root.resolve())
    else:
        if not os.environ.get("CLOUDFLARE_API_TOKEN"):
            raise SystemExit("CLOUDFLARE_API_TOKEN is required for R2 publication")
        backend = WranglerR2Backend(
            bucket=args.bucket,
            command=tuple(shlex.split(args.wrangler_command)),
            cwd=pathlib.Path(__file__).resolve().parents[1],
        )
    published = publish(source_root, backend)
    print(json.dumps({
        "published": len(descriptors),
        "snapshot_key": published["snapshot_key"],
        "manifest_sha256": published["manifest_sha256"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

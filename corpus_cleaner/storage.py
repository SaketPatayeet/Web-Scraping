"""Local and S3 storage helpers for the Stage 2 corpus pipeline."""

import gzip
import json
import os
import time
from pathlib import Path

import boto3
import pyarrow as pa
import pyarrow.parquet as pq


PARQUET_SCHEMA = pa.schema([
    ("id", pa.string()),
    ("url", pa.string()),
    ("canonical_url", pa.string()),
    ("source", pa.string()),
    ("scraped_at", pa.string()),
    ("published_at", pa.string()),
    ("title", pa.string()),
    ("text", pa.string()),
    ("content_hash", pa.string()),
])


# ---------------------------------------------------------------------------
# Local input
# ---------------------------------------------------------------------------

def iter_local_raw_records(raw_dir: Path):
    """Yield (record, source_path) from completed JSONL.gz files."""
    raw_dir = Path(raw_dir)

    for path in sorted(raw_dir.rglob("*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()

                if not line:
                    continue

                try:
                    yield json.loads(line), path
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Invalid JSON in {path}:{line_no}"
                    ) from exc


# ---------------------------------------------------------------------------
# Local Parquet output
# ---------------------------------------------------------------------------

class ParquetShardWriter:
    """Write cleaned records to compressed Parquet shards."""

    def __init__(self, output_dir: Path, shard_size: int = 50_000):
        if shard_size <= 0:
            raise ValueError("shard_size must be > 0")

        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.shard_size = shard_size
        self._buffer = []
        self._shard_index = 0
        self.paths: list[Path] = []

    def add(self, row: dict):
        self._buffer.append(row)

        if len(self._buffer) >= self.shard_size:
            self._flush()

    def _flush(self):
        if not self._buffer:
            return

        table = pa.Table.from_pylist(
            self._buffer,
            schema=PARQUET_SCHEMA,
        )

        out_path = (
            self.output_dir
            / f"part-{self._shard_index:05d}.parquet"
        )

        tmp_path = out_path.with_suffix(
            out_path.suffix + ".tmp"
        )
        
        pq.write_table(
            table,
            tmp_path,
            compression="zstd",
        )

        os.replace(tmp_path, out_path)

        self.paths.append(out_path)
        self._shard_index += 1
        self._buffer = []

    def close(self):
        """Flush the final partial shard and return all shard paths."""
        self._flush()
        return list(self.paths)


# ---------------------------------------------------------------------------
# Raw-file cleanup
# ---------------------------------------------------------------------------

def cleanup_raw_files(
    paths: set[Path],
    retention_days: int,
) -> list[Path]:
    """
    Delete only raw files actually processed by a successful run.

    The retention check prevents newly created raw files from being deleted
    immediately.
    """
    if retention_days < 0:
        raise ValueError("retention_days must be >= 0")

    cutoff = time.time() - retention_days * 86400
    deleted = []

    for path in sorted(paths):
        path = Path(path)

        if (
            path.exists()
            and path.stat().st_mtime < cutoff
        ):
            path.unlink()
            deleted.append(path)

    return deleted


# ---------------------------------------------------------------------------
# S3 publishing
# ---------------------------------------------------------------------------

def upload_parquet_dir(
    local_dir: Path,
    bucket: str,
    region: str,
    prefix: str,
) -> list[str]:
    """Upload every completed Parquet shard under an explicit S3 run prefix."""
    local_dir = Path(local_dir)

    s3 = boto3.client(
        "s3",
        region_name=region,
    )

    uploaded = []

    for path in sorted(local_dir.glob("*.parquet")):
        key = f"{prefix.rstrip('/')}/{path.name}"

        s3.upload_file(
            str(path),
            bucket,
            key,
        )

        uploaded.append(key)

    return uploaded


def upload_manifest(
    bucket: str,
    region: str,
    prefix: str,
    manifest: dict,
) -> str:
    """Upload the run manifest to the same S3 prefix as the Parquet shards."""
    s3 = boto3.client(
        "s3",
        region_name=region,
    )

    key = f"{prefix.rstrip('/')}/_manifest.json"

    body = json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")

    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType="application/json",
    )

    return key
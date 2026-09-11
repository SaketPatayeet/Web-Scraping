"""Stage 2: normalize -> dedup -> local Parquet."""

import argparse
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from corpus_cleaner import storage
from corpus_cleaner.dedup import load_state, save_state
from corpus_cleaner.normalize import clean_text


logger = logging.getLogger("clean_corpus")


def run(
    raw_dir: Path,
    output_dir: Path,
    dedup_state_path: Path,
    shard_size: int = 50_000,
    jaccard_threshold: float = 0.85,
    retention_days: int = 7,
    cleanup: bool = True,
) -> dict:
    """
    Process all local raw JSONL.GZ files into local Parquet shards.

    This function does not upload anything to S3.

    Deduplication state is committed only after all Parquet output has
    been successfully written.
    """

    raw_dir = Path(raw_dir)
    output_root = Path(output_dir)

    run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid.uuid4().hex[:8]
    )

    run_output = output_root / run_id
    run_output.mkdir(parents=True, exist_ok=False)

    stats = {
        "run_id": run_id,
        "read": 0,
        "dropped_empty": 0,
        "dropped_exact_dup": 0,
        "dropped_near_dup": 0,
        "kept": 0,
        "parquet_files": 0,
        "local_raw_deleted": 0,
    }

    processed_raw_files: set[Path] = set()

    dedup_state = load_state(
        dedup_state_path,
        jaccard_threshold=jaccard_threshold,
    )

    writer = storage.ParquetShardWriter(
        run_output,
        shard_size=shard_size,
    )

    try:
        for record, source_path in storage.iter_local_raw_records(raw_dir):
            stats["read"] += 1
            processed_raw_files.add(Path(source_path))

            # Normalize text and remove known boilerplate.
            text = clean_text(record.get("text", ""))

            if not text:
                stats["dropped_empty"] += 1
                continue

            content_hash = hashlib.sha256(
                text.encode("utf-8")
            ).hexdigest()

            dup_check = dedup_state.check_and_add(
                content_hash,
                text,
            )

            if dup_check["is_duplicate"]:
                if dup_check["reason"] == "exact":
                    stats["dropped_exact_dup"] += 1
                else:
                    stats["dropped_near_dup"] += 1

                continue

            row = {
                "id": content_hash[:16],
                "url": record.get("url", ""),
                "canonical_url": record.get("canonical_url", ""),
                "source": record.get("source", ""),
                "scraped_at": record.get("scraped_at", ""),
                "published_at": record.get("published_at", ""),
                "title": record.get("title", ""),
                "text": text,
                "content_hash": content_hash,
            }

            writer.add(row)
            stats["kept"] += 1

        parquet_paths = writer.close()

        stats["parquet_files"] = len(parquet_paths)

        # Commit deduplication state only after local Parquet generation
        # has completed successfully.
        save_state(
            dedup_state,
            dedup_state_path,
        )

        if cleanup:
            deleted = storage.cleanup_raw_files(
                processed_raw_files,
                retention_days,
            )

            stats["local_raw_deleted"] = len(deleted)

        # Local manifest for auditing and manual upload.
        local_manifest = run_output / "_manifest.json"

        local_manifest.write_text(
            json.dumps(
                {
                    **stats,
                    "generated_at": datetime.now(
                        timezone.utc
                    ).isoformat(),
                    "output_directory": str(run_output),
                    "upload_required": True,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        logger.info(
            "stage2 complete: %s",
            stats,
        )

        logger.info(
            "Parquet output generated at: %s",
            run_output,
        )

        return stats

    except Exception:
        logger.exception(
            "stage2 failed for run %s; raw input was left in place "
            "and dedup state was not committed",
            run_id,
        )

        raise


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Clean, deduplicate, and generate local Parquet shards "
            "from the scraped corpus."
        )
    )

    parser.add_argument(
        "--raw-dir",
        default="local/raw",
    )

    parser.add_argument(
        "--output-dir",
        default="local/processed",
    )

    parser.add_argument(
        "--dedup-state",
        default="local/state/dedup_state.pkl",
    )

    parser.add_argument(
        "--shard-size",
        type=int,
        default=50_000,
    )

    parser.add_argument(
        "--jaccard-threshold",
        type=float,
        default=0.85,
    )

    parser.add_argument(
        "--retention-days",
        type=int,
        default=7,
    )

    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Keep processed raw JSONL.GZ files.",
    )

    parser.add_argument(
        "--log-level",
        default="INFO",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level,
        format=(
            "%(asctime)s %(levelname)s "
            "%(name)s: %(message)s"
        ),
    )

    run(
        raw_dir=Path(args.raw_dir),
        output_dir=Path(args.output_dir),
        dedup_state_path=Path(args.dedup_state),
        shard_size=args.shard_size,
        jaccard_threshold=args.jaccard_threshold,
        retention_days=args.retention_days,
        cleanup=not args.no_cleanup,
    )


if __name__ == "__main__":
    main()
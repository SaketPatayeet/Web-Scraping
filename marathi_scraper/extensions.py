"""
Auto-triggers stage 2 (clean/dedup/quality-filter -> Parquet -> S3
upload -> local raw cleanup) when the spider finishes — so running the
scraper is one command, not "run scraper, then remember to run cleaning
separately." See plan.md v2.

Runs in-process via corpus_cleaner.clean_corpus.run(), reusing the same
LOCAL_RAW_DIR the spider just wrote to. A run that finds nothing new
(e.g. every source disabled) still runs stage 2 harmlessly — it'll just
process whatever's on disk, which may be from a prior run's leftovers
within the retention window.

To disable auto-trigger (e.g. to batch several scraper runs before
cleaning once), remove this from EXTENSIONS in settings.py and run
`python -m corpus_cleaner.clean_corpus` manually instead.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class AutoCleanExtension:
    def __init__(self, settings):
        self.settings = settings

    @classmethod
    def from_crawler(cls, crawler):
        ext = cls(crawler.settings)
        crawler.signals.connect(ext.spider_closed, signal=__import__("scrapy").signals.spider_closed)
        return ext

    def spider_closed(self, spider, reason):
        if not self.settings.getbool("AUTO_CLEAN_ON_CLOSE", True):
            return

        if reason != "finished":
            spider.logger.warning(
                f"spider closed with reason={reason!r}, not 'finished' — "
                f"skipping auto-trigger of stage 2 (run it manually once "
                f"you're ready, the local raw JSONL is still on disk)."
            )
            return
        try:
            from corpus_cleaner.clean_corpus import run as run_stage2
        except ImportError as e:
            spider.logger.error(
                f"could not import corpus_cleaner ({e}) — skipping auto-"
                f"trigger of stage 2. Raw JSONL is on disk; run "
                f"`python -m corpus_cleaner.clean_corpus` manually."
            )
            return

        spider.logger.info("spider finished — auto-triggering stage 2 (clean/dedup/export)")

        try:
            stats = run_stage2(
                raw_dir=Path(self.settings.get("LOCAL_RAW_DIR", "local/raw")),
                output_dir=Path(self.settings.get("LOCAL_PROCESSED_DIR", "local/processed")),
                dedup_state_path=Path(self.settings.get("DEDUP_STATE_PATH", "local/state/dedup_state.pkl")),
                bucket=self.settings.get("S3_BUCKET"),
                region=self.settings.get("AWS_REGION", "ap-south-1"),
                shard_size=self.settings.getint("PARQUET_SHARD_SIZE", 50_000),
                jaccard_threshold=self.settings.getfloat("JACCARD_THRESHOLD", 0.75),
                retention_days=self.settings.getint("LOCAL_RAW_RETENTION_DAYS", 7),
            )
        except Exception:
            # Stage 2 failure must not cause the raw safety buffer to be
            # deleted. clean_corpus itself also refuses to commit dedup state
            # until publication succeeds.
            spider.logger.exception(
                "stage 2 failed; raw JSONL was retained. Run corpus_cleaner manually to retry."
            )
            return

        spider.logger.info(f"stage 2 complete: {stats}")

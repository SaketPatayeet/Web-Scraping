"""
Three pipelines, run in order (see settings.py ITEM_PIPELINES):

1. ExtractPipeline   - pulls article text out of raw HTML (trafilatura),
                        computes Devanagari ratio + content hash.
2. FilterPipeline    - drops items that fail language/length checks.
3. LocalJsonlPipeline - batches surviving items into gzip JSONL files,
                        written to LOCAL disk only, partitioned by
                        source/date. NOT uploaded to S3 — see plan.md v2:
                        raw JSONL is a short-lived local artifact that
                        stage 2 (corpus_cleaner) reads directly. Only the
                        cleaned Parquet output reaches S3.

Cleaning/dedup across the whole corpus is NOT done here — this pipeline's
job ends at "clean single record, land it on local disk for stage 2."
Stage 2 is triggered automatically on spider close — see extensions.py.
"""

import gzip
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import trafilatura
from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem

DEVANAGARI_RANGE = (0x0900, 0x097F)


class ExtractPipeline:
    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        html = adapter.get("html", "")

        extracted = trafilatura.extract(html, favor_recall=False) or ""
        adapter["text"] = extracted.strip()
        del adapter["html"]  # don't carry raw HTML into storage — text only

        # Count only alphabetic characters (isalpha()) so matras/combining
        # marks -- which are Devanagari codepoints but not letters -- don't
        # inflate the numerator past the denominator.
        alpha_chars = [c for c in adapter["text"] if c.isalpha()]
        devanagari_chars = [
            c for c in alpha_chars if DEVANAGARI_RANGE[0] <= ord(c) <= DEVANAGARI_RANGE[1]
        ]
        adapter["devanagari_ratio"] = (
            len(devanagari_chars) / len(alpha_chars) if alpha_chars else 0.0
        )
        adapter["content_hash"] = hashlib.sha256(
            adapter["text"].encode("utf-8")
        ).hexdigest()

        return item


class FilterPipeline:
    def __init__(self, min_devanagari_ratio, min_text_length):
        self.min_devanagari_ratio = min_devanagari_ratio
        self.min_text_length = min_text_length

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            min_devanagari_ratio=crawler.settings.getfloat("MIN_DEVANAGARI_RATIO", 0.4),
            min_text_length=crawler.settings.getint("MIN_TEXT_LENGTH", 200),
        )

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        text = adapter.get("text", "")

        if len(text) < self.min_text_length:
            raise DropItem(f"Too short ({len(text)} chars): {adapter.get('url')}")

        if adapter.get("devanagari_ratio", 0.0) < self.min_devanagari_ratio:
            raise DropItem(
                f"Devanagari ratio {adapter.get('devanagari_ratio'):.2f} "
                f"below threshold: {adapter.get('url')}"
            )

        return item


class LocalJsonlPipeline:
    """
    Buffers items per source in memory, flushes to a local .jsonl.gz file
    every FLUSH_EVERY items (and always on spider close). Writes to local
    disk ONLY — no S3 upload here. Partitioned the same way the old raw
    S3 zone was, just kept local: local/raw/{source}/{yyyy}/{mm}/{dd}/{batch_id}.jsonl.gz

    Stage 2 (corpus_cleaner) reads directly from this local directory.
    """

    def __init__(self, flush_every, local_dir):
        self.flush_every = flush_every
        self.local_dir = Path(local_dir)
        self.buffers = defaultdict(list)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            flush_every=crawler.settings.getint("LOCAL_FLUSH_EVERY", 500),
            local_dir=crawler.settings.get("LOCAL_RAW_DIR", "local/raw"),
        )

    def open_spider(self, spider):
        self.local_dir.mkdir(parents=True, exist_ok=True)

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        source = adapter.get("source", "unknown")
        self.buffers[source].append(dict(adapter))

        if len(self.buffers[source]) >= self.flush_every:
            self._flush(source, spider)

        return item

    def close_spider(self, spider):
        for source in list(self.buffers.keys()):
            if self.buffers[source]:
                self._flush(source, spider)

    def _flush(self, source, spider):
        records = self.buffers[source]
        self.buffers[source] = []

        now = datetime.now(timezone.utc)
        batch_id = hashlib.sha1(f"{source}{now.isoformat()}".encode()).hexdigest()[:12]
        filename = f"{batch_id}.jsonl.gz"

        partition_dir = self.local_dir / source / f"{now.year:04d}" / f"{now.month:02d}" / f"{now.day:02d}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        local_path = partition_dir / filename

        tmp_path = local_path.with_suffix(local_path.suffix + ".tmp")
        with gzip.open(tmp_path, "wt", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        tmp_path.replace(local_path)

        spider.logger.info(f"wrote {len(records)} records -> {local_path}")

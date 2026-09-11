import os
from dotenv import load_dotenv

load_dotenv()

BOT_NAME = "marathi_scraper"
SPIDER_MODULES = ["marathi_scraper.spiders"]
NEWSPIDER_MODULE = "marathi_scraper.spiders"

# Crawl responsibly.
ROBOTSTXT_OBEY = True
CONCURRENT_REQUESTS_PER_DOMAIN = 4
DOWNLOAD_DELAY = 1.0
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1.0
AUTOTHROTTLE_MAX_DELAY = 10.0
AUTOTHROTTLE_TARGET_CONCURRENCY = 2.0

USER_AGENT = os.environ.get(
    "SCRAPER_USER_AGENT",
    "MarathiFinCorpusBot/1.0 (+contact: replace-with-real-contact)",
)

# Scrapy's request/scheduler state. Keep this directory between restarts.
JOBDIR = os.environ.get(
    "SCRAPY_JOBDIR",
    "local/crawl_state/finance_spider",
)

DEPTH_LIMIT = 0

FEED_EXPORT_ENCODING = "utf-8"

# Stage 1:
# Extract article text -> apply cheap language/length filters
# -> write surviving records to local JSONL.gz.
ITEM_PIPELINES = {
    "marathi_scraper.pipelines.ExtractPipeline": 100,
    "marathi_scraper.pipelines.FilterPipeline": 200,
    "marathi_scraper.pipelines.LocalJsonlPipeline": 300,
}

#EXTENSIONS = {
#    "marathi_scraper.extensions.AutoCleanExtension": 500,
#}

# Stage 2 is intentionally NOT triggered automatically.
# Run it separately with:
#
#   python -m corpus_cleaner.clean_corpus
#
# This lets you run several scraping jobs and then clean/deduplicate
# the accumulated local raw corpus in one batch.

# Stage-1 cheap filters.
# These only prevent obviously bad records from reaching disk.
MIN_DEVANAGARI_RATIO = 0.4
MIN_TEXT_LENGTH = 200

# Temporary Stage-1 storage.
LOCAL_RAW_DIR = "local/raw"
LOCAL_FLUSH_EVERY = 500
LOCAL_RAW_RETENTION_DAYS = 7

# Stage-2 storage/state.
LOCAL_PROCESSED_DIR = "local/processed"
DEDUP_STATE_PATH = "local/state/dedup_state.pkl"
PARQUET_SHARD_SIZE = 50_000
JACCARD_THRESHOLD = 0.85

# S3 is used only for final processed Parquet output.
S3_BUCKET = os.environ.get("S3_BUCKET", "")
AWS_REGION = os.environ.get(
    "AWS_DEFAULT_REGION",
    "ap-south-1",
)

# Optional logging configuration.
# LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
# LOG_FILE = "crawl.log"
# Marathi Financial Scraper

Scrapes financial content from configured Marathi-language sources, extracts
article text, filters for language/length, and lands it in S3 as gzip JSONL —
partitioned by source and date. Cleaning/dedup across the corpus is a
separate, later stage (not part of this project).

## Setup

```bash
pip install -r requirements.txt
aws configure   # or set AWS env vars — needs s3:PutObject on the target bucket
```

Set your bucket in `marathi_scraper/settings.py` (`S3_BUCKET`) or export
`SCRAPY_S3_BUCKET`-style overrides as needed.


## Run

```bash
cd marathi_scraper
scrapy crawl finance_spider
```

Resume a crashed crawl by setting `JOBDIR` in settings.py before running
again with the same directory.

## Output

```
s3://<bucket>/raw/{source}/{yyyy}/{mm}/{dd}/{batch_id}.jsonl.gz
```

Each line:
```json
{"url": "...", "source": "...", "scraped_at": "...", "title": "...", "text": "...", "devanagari_ratio": 0.91, "content_hash": "..."}
```

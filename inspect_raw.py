import gzip
import json
import re
from pathlib import Path

# Install once if needed:
# pip install transformers

from transformers import AutoTokenizer


FILES = [
    Path(
        r"D:\Projects\marathi_scraper\marathi_scraper\local\raw\economic_times_marathi\2026\09\11\623f7f8d2fe3.jsonl.gz"
    ),
    Path(
        r"D:\Projects\marathi_scraper\marathi_scraper\local\raw\loksatta_business\2026\09\11\153eb606dc36.jsonl.gz"
    ),
    Path(
        r"D:\Projects\marathi_scraper\marathi_scraper\local\raw\mr_wikipedia_finance\2026\09\11\f4a46bcd2a67.jsonl.gz"
    ),
    Path(
        r"D:\Projects\marathi_scraper\marathi_scraper\local\raw\sakal_finance\2026\09\11\fcc48b0ee662.jsonl.gz"
    ),
]

# Rough token estimate.
# This is not necessarily the tokenizer used by your final model.
tokenizer = AutoTokenizer.from_pretrained("gpt2")


def format_number(value):
    return f"{value:,}"


def format_bytes(num_bytes):
    units = ["B", "KB", "MB", "GB", "TB"]

    size = float(num_bytes)

    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.2f} {unit}"

        size /= 1024


def count_words(text):
    return len(re.findall(r"\S+", text))


def inspect_file(path):
    if not path.exists():
        print(f"\nFILE NOT FOUND: {path}")
        return None

    file_size = path.stat().st_size

    article_count = 0
    total_characters = 0
    total_words = 0
    total_tokens = 0

    first_record = None

    with gzip.open(path, "rt", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()

            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                print(
                    f"Invalid JSON in {path.name}, "
                    f"line {line_number}: {error}"
                )
                continue

            if first_record is None:
                first_record = record

            # Your pipeline should produce "text".
            # The fallback handles files that may still contain "html".
            text = (
                record.get("text")
                or record.get("content")
                or record.get("html")
                or ""
            )

            if not isinstance(text, str):
                text = str(text)

            article_count += 1
            total_characters += len(text)
            total_words += count_words(text)

            # add_special_tokens=False gives a cleaner corpus estimate
            # without BOS/EOS tokens for every article.
            total_tokens += len(
                tokenizer.encode(
                    text,
                    add_special_tokens=False,
                )
            )

    average_characters = (
        total_characters / article_count
        if article_count
        else 0
    )

    average_words = (
        total_words / article_count
        if article_count
        else 0
    )

    average_tokens = (
        total_tokens / article_count
        if article_count
        else 0
    )

    print("\n" + "=" * 80)
    print(f"FILE: {path.name}")
    print(f"PATH: {path}")
    print("-" * 80)
    print(f"Size on disk:          {format_bytes(file_size)}")
    print(f"Number of articles:    {format_number(article_count)}")
    print(f"Total characters:      {format_number(total_characters)}")
    print(f"Total words:           {format_number(total_words)}")
    print(f"Estimated GPT-2 tokens:{format_number(total_tokens)}")
    print(f"Average characters:    {average_characters:,.2f}")
    print(f"Average words:         {average_words:,.2f}")
    print(f"Average tokens:        {average_tokens:,.2f}")

    if first_record:
        print("\nFIRST RECORD KEYS:")
        print(list(first_record.keys()))

        print("\nFIRST RECORD PREVIEW:")
        print(json.dumps(
            first_record,
            ensure_ascii=False,
            indent=2,
        )[:3000])

    return {
        "file": path.name,
        "size_bytes": file_size,
        "articles": article_count,
        "characters": total_characters,
        "words": total_words,
        "estimated_tokens": total_tokens,
    }


def main():
    results = []

    for path in FILES:
        result = inspect_file(path)

        if result:
            results.append(result)

    if not results:
        print("No files were successfully inspected.")
        return

    total_size = sum(row["size_bytes"] for row in results)
    total_articles = sum(row["articles"] for row in results)
    total_characters = sum(row["characters"] for row in results)
    total_words = sum(row["words"] for row in results)
    total_tokens = sum(row["estimated_tokens"] for row in results)

    print("\n" + "=" * 80)
    print("TOTAL")
    print("=" * 80)
    print(f"Files:                 {len(results)}")
    print(f"Total size on disk:    {format_bytes(total_size)}")
    print(f"Total articles:        {format_number(total_articles)}")
    print(f"Total characters:      {format_number(total_characters)}")
    print(f"Total words:           {format_number(total_words)}")
    print(f"Estimated GPT-2 tokens:{format_number(total_tokens)}")


if __name__ == "__main__":
    main()
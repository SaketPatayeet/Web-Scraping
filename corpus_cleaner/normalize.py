"""
Text normalization and rule-based boilerplate stripping.

Normalization is performed before deduplication so that exact hashes,
near-duplicate shingles, and the final stored text all operate on the
same cleaned representation.

Order:
    1. Normalize Unicode and whitespace.
    2. Remove known boilerplate lines.
    3. Re-collapse blank lines left behind by removed lines.
"""

import re
import unicodedata


_INVISIBLE_CHARS = "".join([
    "\u200b",  # zero-width space
    "\u2060",  # word joiner
    "\ufeff",  # BOM
])

_INVISIBLE_RE = re.compile(f"[{_INVISIBLE_CHARS}]")
_NBSP_RE = re.compile("[\u00a0\u202f]")
_MULTI_BLANK_LINE_RE = re.compile(r"\n{3,}")
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")
_TRAILING_SPACE_RE = re.compile(r"[ \t]+\n")


_BOILERPLATE_PATTERNS = [
    r"^अधिक\s+वाचा\s*:?.*$",
    r"^संबंधित\s+बातम्या\s*:?.*$",
    r"^हे\s+ही\s+वाचा\s*:?.*$",
    r"^शेअर\s+करा\s*:?.*$",
    r"^सबस्क्राइब\s+करा\s*:?.*$",
    r"^कॉपीराइट\s*©.*$",
    r"^©.*(?:all rights reserved).*$",
    r"^disclaimer\s*:?.*$",
    r"^अस्वीकरण\s*:?.*$",
    r"^सूचना\s*:\s*(?:हा|वरील).*(?:सल्ला नाही).*$",
    r"^click here.*$",
    r"^इथे\s+क्लिक\s+करा.*$",
    r"^read more.*$",
    r"^loading\.{0,3}$",
    r"^advertisement$",
    r"^जाहिरात$",
]

_BOILERPLATE_RE = re.compile(
    "|".join(f"(?:{pattern})" for pattern in _BOILERPLATE_PATTERNS),
    re.IGNORECASE,
)


def normalize_text(text: str) -> str:
    """Normalize Unicode and whitespace. Idempotent."""
    if not text:
        return ""

    text = unicodedata.normalize("NFC", text)

    # Remove characters that are generally extraction/encoding artifacts.
    # ZWJ/ZWNJ are intentionally preserved because they can be legitimate
    # in Indic text.
    text = _INVISIBLE_RE.sub("", text)

    # Normalize non-breaking spaces.
    text = _NBSP_RE.sub(" ", text)

    # Normalize line endings.
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Remove trailing spaces from lines.
    text = _TRAILING_SPACE_RE.sub("\n", text)

    # Collapse repeated spaces/tabs.
    text = _MULTI_SPACE_RE.sub(" ", text)

    # Collapse excessive blank lines while preserving paragraph breaks.
    text = _MULTI_BLANK_LINE_RE.sub("\n\n", text)

    return text.strip()


def strip_boilerplate(text: str) -> str:
    """
    Remove lines matching known boilerplate patterns.

    Operates on already-normalized text.
    """
    if not text:
        return ""

    kept_lines = []

    for line in text.split("\n"):
        stripped = line.strip()

        if stripped and _BOILERPLATE_RE.match(stripped):
            continue

        kept_lines.append(line)

    cleaned = "\n".join(kept_lines)

    # Removing boilerplate lines can leave excessive blank lines.
    cleaned = _MULTI_BLANK_LINE_RE.sub("\n\n", cleaned)

    return cleaned.strip()


def clean_text(text: str) -> str:
    """Normalize text and remove known boilerplate."""
    return strip_boilerplate(normalize_text(text))
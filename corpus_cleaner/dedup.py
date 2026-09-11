"""Persistent document-level exact + near-duplicate detection.

The persisted state represents documents that have actually been published
into the corpus.  The caller should therefore save it only after the output
for a run has been successfully published (locally or to S3).

Near-duplicate detection uses MinHash LSH as a candidate generator and then
verifies candidates with exact word-shingle Jaccard similarity.  LSH itself
is probabilistic and must not be treated as an exact similarity decision.
"""

import pickle
from pathlib import Path

from datasketch import MinHash, MinHashLSH

_NUM_PERM = 128
_SHINGLE_SIZE = 4


def _shingles(text: str, k: int = _SHINGLE_SIZE):
    words = text.split()
    if len(words) < k:
        if words:
            yield " ".join(words)
        return
    for i in range(len(words) - k + 1):
        yield " ".join(words[i:i + k])


def _shingle_set(text: str) -> set[str]:
    return set(_shingles(text))


def _minhash_for(text: str) -> MinHash:
    mh = MinHash(num_perm=_NUM_PERM)
    for shingle in _shingles(text):
        mh.update(shingle.encode("utf-8"))
    return mh


class DedupState:
    """Picklable exact-hash set + MinHash LSH + representative shingle sets."""

    def __init__(self, jaccard_threshold: float = 0.85):
        if not 0.0 < jaccard_threshold <= 1.0:
            raise ValueError("jaccard_threshold must be in (0, 1]")
        self.jaccard_threshold = jaccard_threshold
        self.seen_hashes: set[str] = set()
        self.lsh = MinHashLSH(threshold=jaccard_threshold, num_perm=_NUM_PERM)
        self._shingles_by_id: dict[str, set[str]] = {}
        self._next_id = 0

    def check_and_add(self, content_hash: str, text: str) -> dict:
        """Return duplicate status and register *only* a new representative.

        The LSH query produces candidates. Exact Jaccard against those
        candidates decides whether the document is really a near duplicate.
        """
        if content_hash in self.seen_hashes:
            return {"is_duplicate": True, "reason": "exact"}

        shingles = _shingle_set(text)
        mh = _minhash_for(text)
        near_matches = self.lsh.query(mh)

        for doc_id in near_matches:
            existing = self._shingles_by_id.get(doc_id)
            if not existing:
                continue
            union = shingles | existing
            similarity = len(shingles & existing) / len(union) if union else 1.0
            if similarity >= self.jaccard_threshold:
                return {
                    "is_duplicate": True,
                    "reason": "near_dup",
                    "jaccard": similarity,
                }

        self.seen_hashes.add(content_hash)
        doc_id = f"doc_{self._next_id}"
        self._next_id += 1
        self._shingles_by_id[doc_id] = shingles
        self.lsh.insert(doc_id, mh)
        return {"is_duplicate": False, "reason": None}


def load_state(path: Path, jaccard_threshold: float = 0.85) -> DedupState:
    path = Path(path)
    if not path.exists():
        return DedupState(jaccard_threshold=jaccard_threshold)

    with open(path, "rb") as f:
        state = pickle.load(f)
    if not isinstance(state, DedupState):
        raise TypeError(f"Unsupported dedup state type: {type(state)!r}")
    if state.jaccard_threshold != jaccard_threshold:
        raise ValueError(
            f"Persisted dedup state was built with jaccard_threshold="
            f"{state.jaccard_threshold}, but {jaccard_threshold} was requested. "
            "Delete/rebuild the state if you intentionally changed the threshold."
        )
    return state


def save_state(state: DedupState, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "wb") as f:
        pickle.dump(state, f, protocol=pickle.HIGHEST_PROTOCOL)
    tmp_path.replace(path)

import pickle

with open("local/state/dedup_state.pkl", "rb") as f:
    state = pickle.load(f)

print(f"Type: {type(state).__name__}")
print(f"Jaccard threshold: {state.jaccard_threshold}")
print(f"Documents: {len(state.seen_hashes):,}")
print(f"Representatives: {len(state._shingles_by_id):,}")
print(f"Next ID: {state._next_id:,}")
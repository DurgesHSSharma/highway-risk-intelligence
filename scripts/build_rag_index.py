"""Phase 8: build the local FAISS retrieval index over the Phase 7 chunk
dataset (data/processed/document_chunks.csv).

Generates local sentence-transformers/all-MiniLM-L6-v2 embeddings for every
included chunk (empty/near-empty chunks excluded; suspicious_text /
low_ocr_quality chunks kept and flagged), builds an exact FAISS IndexFlatIP
over L2-normalized embeddings, and writes:

    rag_index/document_chunks.faiss
    rag_index/embeddings.npy
    rag_index/metadata.json   (vector -> chunk/document/page/citation mapping)

Skips regeneration if the source CSV and embedding-model identity are
unchanged (pass --force to rebuild anyway).

Usage (from repo root, using the existing backend/.venv):
    ./backend/.venv/Scripts/python.exe -m scripts.build_rag_index
    ./backend/.venv/Scripts/python.exe -m scripts.build_rag_index --force
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"

# The embedding/index logic lives under backend/app/rag so the API and this
# build script share exactly one implementation -- never redefine it here.
# backend/ is not on sys.path when this script is run from the repo root, so
# it must be added explicitly (same pattern as scripts/load_db.py).
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.rag.config import DOCUMENT_CHUNKS_CSV_PATH, RAG_INDEX_DIR  # noqa: E402
from app.rag.index_builder import build_index  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DOCUMENT_CHUNKS_CSV_PATH)
    parser.add_argument("--output-dir", type=Path, default=RAG_INDEX_DIR)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild even if the source CSV / embedding model identity is unchanged.",
    )
    args = parser.parse_args()

    print(f"Source chunk dataset: {args.csv}")
    summary = build_index(csv_path=args.csv, output_dir=args.output_dir, force=args.force)

    if summary.skipped_rebuild:
        print("Source CSV and embedding model unchanged -- reused existing index (pass --force to rebuild).")
    else:
        print("Built new index.")
    print()
    print(f"  total chunks:          {summary.total_chunks}")
    print(f"  excluded (empty/near): {summary.excluded_count}")
    print(f"  included:              {summary.included_count}")
    print(f"  flagged (quality):     {summary.flagged_count}")
    print(f"  vectors indexed:       {summary.vector_count}")
    print(f"  mapping entries:       {summary.mapping_count}")
    print(f"  embedding model:       {summary.embedding_model}")
    print(f"  embedding dim:         {summary.embedding_dim}")
    print(f"  normalization:         {summary.normalization}")
    print(f"  similarity metric:     {summary.similarity_metric}")
    print(f"  index type:            {summary.index_type}")
    print(f"  output dir:            {args.output_dir}")

    ok = summary.vector_count == summary.mapping_count == summary.included_count
    print()
    print("VALIDATION: " + ("PASS -- vector/mapping/included counts match." if ok else "FAIL -- see counts above."))
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()

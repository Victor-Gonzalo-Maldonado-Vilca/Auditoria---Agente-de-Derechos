#!/usr/bin/env python3
"""RAG vectorial local y reproducible para las referencias del skill DSAR.

Fragmenta documentos Markdown, genera embeddings TF-IDF normalizados de
unigramas y bigramas, persiste un indice vectorial JSON y recupera contexto
mediante similitud coseno. Solo utiliza la biblioteca estandar de Python.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = PROJECT_ROOT / "skills" / "dsar-rights" / "references"
DEFAULT_INDEX = Path(__file__).resolve().with_name("vector_store.json")
MODEL_NAME = "tfidf-word-ngram-1-2-v1"
TOKEN_RE = re.compile(r"[a-z0-9]{2,}")
STOPWORDS = {
    "al", "ante", "como", "con", "de", "del", "el", "en", "es", "esta",
    "este", "la", "las", "lo", "los", "para", "por", "que", "se", "sin",
    "su", "sus", "un", "una", "y",
}


def normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def tokenize(value: str) -> list[str]:
    words = [token for token in TOKEN_RE.findall(normalize(value)) if token not in STOPWORDS]
    bigrams = [f"{left}::{right}" for left, right in zip(words, words[1:])]
    return words + bigrams


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def corpus_signature(corpus_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(corpus_dir.rglob("*.md")):
        digest.update(path.relative_to(corpus_dir).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def split_markdown(path: Path, root: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    relative = path.relative_to(root).as_posix()
    sections: list[tuple[str, list[str]]] = []
    heading = path.stem.replace("-", " ").title()
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith("#"):
            if any(item.strip() for item in body):
                sections.append((heading, body))
            heading = line.lstrip("#").strip() or heading
            body = []
        else:
            body.append(line)
    if any(item.strip() for item in body):
        sections.append((heading, body))

    chunks = []
    for index, (section, lines) in enumerate(sections, start=1):
        content = "\n".join(lines).strip()
        if content:
            chunks.append(
                {
                    "chunk_id": f"{path.stem}-{index:02d}",
                    "source": relative,
                    "section": section,
                    "text": content,
                    "sha256": sha256_text(content),
                }
            )
    return chunks


def load_chunks(corpus_dir: Path = DEFAULT_CORPUS) -> list[dict[str, str]]:
    if not corpus_dir.is_dir():
        raise ValueError(f"No existe el corpus RAG: {corpus_dir}")
    chunks: list[dict[str, str]] = []
    for path in sorted(corpus_dir.rglob("*.md")):
        chunks.extend(split_markdown(path, corpus_dir))
    if not chunks:
        raise ValueError("El corpus RAG no contiene documentos Markdown")
    return chunks


def sparse_embedding(
    terms: list[str], vocabulary: dict[str, int], idf: list[float]
) -> list[list[float]]:
    counts = Counter(term for term in terms if term in vocabulary)
    if not counts:
        return []
    weights = {
        vocabulary[term]: (1.0 + math.log(frequency)) * idf[vocabulary[term]]
        for term, frequency in counts.items()
    }
    norm = math.sqrt(sum(weight * weight for weight in weights.values()))
    return [[index, round(weight / norm, 10)] for index, weight in sorted(weights.items())]


def build_index(
    corpus_dir: Path = DEFAULT_CORPUS, index_path: Path = DEFAULT_INDEX
) -> dict[str, Any]:
    chunks = load_chunks(corpus_dir)
    tokenized = [tokenize(chunk["text"]) for chunk in chunks]
    document_frequency: Counter[str] = Counter()
    for terms in tokenized:
        document_frequency.update(set(terms))
    vocabulary_terms = sorted(document_frequency)
    vocabulary = {term: index for index, term in enumerate(vocabulary_terms)}
    count = len(chunks)
    idf = [
        round(math.log((1 + count) / (1 + document_frequency[term])) + 1.0, 10)
        for term in vocabulary_terms
    ]
    indexed_chunks = []
    for chunk, terms in zip(chunks, tokenized):
        indexed_chunks.append(
            {**chunk, "vector": sparse_embedding(terms, vocabulary, idf)}
        )
    index = {
        "format_version": 1,
        "embedding_model": MODEL_NAME,
        "similarity": "cosine",
        "corpus": str(corpus_dir.relative_to(PROJECT_ROOT).as_posix())
        if corpus_dir.is_relative_to(PROJECT_ROOT)
        else str(corpus_dir),
        "corpus_sha256": corpus_signature(corpus_dir),
        "dimensions": len(vocabulary_terms),
        "vocabulary": vocabulary_terms,
        "idf": idf,
        "chunks": indexed_chunks,
    }
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        json.dumps(index, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return index


def load_index(
    corpus_dir: Path = DEFAULT_CORPUS,
    index_path: Path = DEFAULT_INDEX,
    rebuild: bool = False,
) -> dict[str, Any]:
    signature = corpus_signature(corpus_dir)
    if not rebuild and index_path.is_file():
        index = json.loads(index_path.read_text(encoding="utf-8"))
        if (
            index.get("format_version") == 1
            and index.get("embedding_model") == MODEL_NAME
            and index.get("corpus_sha256") == signature
        ):
            return index
    return build_index(corpus_dir, index_path)


def cosine_sparse(left: list[list[float]], right: list[list[float]]) -> float:
    left_map = {int(index): float(value) for index, value in left}
    right_map = {int(index): float(value) for index, value in right}
    if len(left_map) > len(right_map):
        left_map, right_map = right_map, left_map
    return sum(value * right_map.get(index, 0.0) for index, value in left_map.items())


def vector_search(query: str, index: dict[str, Any], top_k: int = 3) -> list[dict]:
    if top_k <= 0:
        raise ValueError("top_k debe ser positivo")
    vocabulary = {term: position for position, term in enumerate(index["vocabulary"])}
    query_vector = sparse_embedding(tokenize(query), vocabulary, index["idf"])
    if not query_vector:
        return []
    scored = [
        (cosine_sparse(query_vector, chunk["vector"]), chunk)
        for chunk in index["chunks"]
    ]
    scored = [item for item in scored if item[0] > 0]
    scored.sort(key=lambda item: (-item[0], item[1]["chunk_id"]))
    results = []
    for rank, (score, chunk) in enumerate(scored[:top_k], start=1):
        excerpt = re.sub(r"\s+", " ", chunk["text"]).strip()
        results.append(
            {
                "rank": rank,
                "score": round(score, 6),
                "chunk_id": chunk["chunk_id"],
                "source": chunk["source"],
                "section": chunk["section"],
                "sha256": chunk["sha256"],
                "excerpt": excerpt[:600],
            }
        )
    return results


def retrieve(
    query: str,
    top_k: int = 3,
    corpus_dir: Path = DEFAULT_CORPUS,
    index_path: Path = DEFAULT_INDEX,
    rebuild: bool = False,
) -> dict:
    index = load_index(corpus_dir, index_path, rebuild)
    index_hash = hashlib.sha256(index_path.read_bytes()).hexdigest()
    return {
        "enabled": True,
        "method": "Busqueda vectorial TF-IDF con similitud coseno",
        "embedding_model": index["embedding_model"],
        "query": query,
        "corpus": index["corpus"],
        "vector_store": str(index_path.relative_to(PROJECT_ROOT).as_posix())
        if index_path.is_relative_to(PROJECT_ROOT)
        else str(index_path),
        "vector_store_sha256": index_hash,
        "vector_dimensions": index["dimensions"],
        "documents_indexed": len({chunk["source"] for chunk in index["chunks"]}),
        "chunks_indexed": len(index["chunks"]),
        "retrieved_chunks": vector_search(query, index, top_k),
    }


def format_context(result: dict) -> str:
    blocks = []
    for item in result["retrieved_chunks"]:
        blocks.append(
            f"[Fuente: {item['source']} | Seccion: {item['section']} | "
            f"Chunk: {item['chunk_id']} | Coseno: {item['score']}]\n{item['excerpt']}"
        )
    return "\n\n".join(blocks)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True, help="Consulta de recuperacion")
    parser.add_argument("--top-k", type=int, default=3, help="Fragmentos a recuperar")
    parser.add_argument("--json", action="store_true", help="Mostrar resultado JSON")
    parser.add_argument(
        "--rebuild-index", action="store_true", help="Regenerar el indice vectorial"
    )
    args = parser.parse_args()
    result = retrieve(args.query, args.top_k, rebuild=args.rebuild_index)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Consulta: {result['query']}")
        print(
            f"Indice: {result['documents_indexed']} documentos, "
            f"{result['chunks_indexed']} fragmentos, "
            f"{result['vector_dimensions']} dimensiones"
        )
        print("\n" + (format_context(result) or "Sin resultados."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

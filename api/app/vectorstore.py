"""
The vector store.

Small enough to be worth writing rather than installing. The whole thing is
"embed some text, save the numbers, compare them with a dot product" — pulling
in Chroma or FAISS for a few hundred chunks would add a dependency and hide the
one interesting line.

Two embedders live here:

  * ModelEmbedder — a real embedding model through the LLM gateway. This is
    what gives you actual semantic search, where "cozy autumn pieces" finds a
    hoodie without either word appearing in it.
  * TfidfEmbedder — a scikit-learn fallback for when no model is reachable. It
    matches on words rather than meaning, so it's noticeably worse, but it
    means a fresh clone with nothing installed still retrieves and still cites.

Which one built the index is stored on every chunk, so the two never get mixed.
"""

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sqlmodel import Session, select

from app.config import settings
from app.llm import llm
from app.models import Chunk


def pack(vector: list[float] | np.ndarray) -> bytes:
    """Vectors go into the database as raw float32 — compact and portable."""
    return np.asarray(vector, dtype=np.float32).tobytes()


def unpack(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def normalise(matrix: np.ndarray) -> np.ndarray:
    """
    Scale every row to length 1.

    Once vectors are unit length, cosine similarity is just a dot product,
    which is why the search function below is one line.
    """
    norms = np.linalg.norm(matrix, axis=-1, keepdims=True)
    return matrix / np.maximum(norms, 1e-10)


class ModelEmbedder:
    """
    Embeddings from a real model, through the gateway.

    Some models — nomic being the common one — are trained with a prefix
    saying whether the text is a document being stored or a question being
    asked, and they get noticeably worse without it. Leaving the prefixes off
    was why a search for "warm layer for winter" wasn't returning the hoodie.
    """

    name = f"model:{settings.llm_embed_model}"

    def _prefix(self, kind: str) -> str:
        if "nomic" not in settings.llm_embed_model.lower():
            return ""
        return "search_query: " if kind == "query" else "search_document: "

    async def embed(self, texts: list[str], kind: str = "document") -> np.ndarray:
        prefix = self._prefix(kind)
        vectors = await llm.embed([f"{prefix}{text}" for text in texts])
        return normalise(np.asarray(vectors, dtype=np.float32))


class TfidfEmbedder:
    """
    Offline fallback. Matches words, not meaning.

    It has to be fitted on the corpus before it can embed anything, including
    queries — that's the trade for not needing a model.
    """

    name = "tfidf"

    def __init__(self) -> None:
        self._vectorizer: TfidfVectorizer | None = None

    def fit(self, corpus: list[str]) -> None:
        self._vectorizer = TfidfVectorizer(
            max_features=1024,
            stop_words="english",
            ngram_range=(1, 2),
        )
        self._vectorizer.fit(corpus)

    async def embed(self, texts: list[str], kind: str = "document") -> np.ndarray:
        # `kind` is ignored here — TF-IDF has no notion of query vs document.
        if self._vectorizer is None:
            raise RuntimeError("TfidfEmbedder.fit() has to be called first")
        dense = self._vectorizer.transform(texts).toarray().astype(np.float32)
        return normalise(dense)


async def resolve_embedder() -> ModelEmbedder | TfidfEmbedder:
    """
    Use a real embedding model if one answers, otherwise fall back.

    Checked by actually embedding a word rather than by pinging /models — a
    provider can be up and still not serve the embedding model we asked for.
    """
    try:
        await llm.embed(["test"])
        return ModelEmbedder()
    except Exception:
        # Deliberately broad: whatever went wrong, the fallback is the answer.
        return TfidfEmbedder()


def index_embedder_name(session: Session) -> str | None:
    """Which embedder built the index that's currently stored?"""
    row = session.exec(select(Chunk.embedder).limit(1)).first()
    return row


def load_matrix(session: Session) -> tuple[list[Chunk], np.ndarray]:
    """Every chunk plus its vectors, stacked into one array for searching."""
    chunks = session.exec(select(Chunk)).all()
    if not chunks:
        return [], np.zeros((0, 0), dtype=np.float32)

    matrix = np.vstack([unpack(chunk.embedding) for chunk in chunks])
    return list(chunks), matrix


def search(
    query_vector: np.ndarray,
    chunks: list[Chunk],
    matrix: np.ndarray,
    k: int = 4,
    min_score: float = 0.05,
) -> list[tuple[Chunk, float]]:
    """
    Top k chunks by cosine similarity.

    Both sides are already unit length, so the dot product is the cosine. The
    floor drops results that only matched noise — better to tell the owner we
    don't know than to cite something irrelevant.
    """
    if not chunks or matrix.size == 0:
        return []

    scores = matrix @ query_vector.ravel()
    best = np.argsort(scores)[::-1][:k]

    return [(chunks[i], float(scores[i])) for i in best if scores[i] >= min_score]

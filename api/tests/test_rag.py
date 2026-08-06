"""
Tests for chunking and retrieval.

Two things here are worth guarding, because both were bugs that made the
copilot cite the wrong document while looking perfectly healthy:

  * thin sections have to merge, or a one-sentence heading ranks nowhere
  * one source must not be able to fill every result slot

Neither needs a model. The embedder is faked so the test controls the ranking
and checks what retrieval does with it.
"""

import numpy as np
import pytest
from sqlmodel import Session, SQLModel, create_engine

from app import rag, vectorstore
from app.models import Chunk

# --- chunking ---


def test_short_sections_merge_into_one_chunk():
    text = """# Shipping

## UK
Free over £75.

## Europe
£12 flat, 5-9 working days.

## Rest of world
£18 flat.
"""
    chunks = rag.split_markdown(text, "shipping")

    # All three are tiny, so they belong together — on their own none of them
    # carries enough language to be found.
    assert len(chunks) == 1
    title, body = chunks[0]
    assert "UK" in title and "Europe" in title
    assert "£12 flat" in body and "£18 flat" in body


def test_a_long_section_stays_on_its_own():
    long_body = "\n\n".join(["a sentence about returns." * 12 for _ in range(4)])
    text = f"# Returns\n\n## The window\n{long_body}\n"

    chunks = rag.split_markdown(text, "returns")

    assert len(chunks) > 1
    assert all("Returns › The window" == title for title, _ in chunks)
    assert all(len(body) <= rag.MAX_CHUNK_CHARS + 200 for _, body in chunks)


def test_the_document_title_comes_from_the_h1():
    chunks = rag.split_markdown("# Sizing\n\n## Fit\nRuns small.\n", "sizing")
    assert chunks[0][0].startswith("Sizing › ")


# --- retrieval ---


class FakeEmbedder:
    """
    Returns whatever vector the test asked for.

    Keyed by text so a test can set up an exact ranking and then assert on
    what retrieval selects from it.
    """

    name = "fake"

    def __init__(self, vectors: dict[str, list[float]]):
        self.vectors = vectors

    async def embed(self, texts, kind="document"):
        return np.asarray([self.vectors[text] for text in texts], dtype=np.float32)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")  # in memory, thrown away after
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def add_chunk(session, source, title, vector):
    session.add(
        Chunk(
            source=source,
            title=title,
            text=f"body of {title}",
            embedder="fake",
            dim=len(vector),
            embedding=vectorstore.pack(vector),
        )
    )


@pytest.mark.asyncio
async def test_retrieval_does_not_let_one_source_fill_every_slot(session, monkeypatch):
    """
    The catalogue bug: fourteen near-identical product chunks used to take
    every slot, pushing the one document that answered the question out.

    There have to be enough other sources to fill k, which is the real
    situation — four knowledge files plus the catalogue. With only two sources
    the cap correctly relaxes rather than returning fewer results than asked
    for, and that case is covered by its own test below.
    """
    # Four catalogue chunks all score higher than anything else.
    for i, score in enumerate([0.99, 0.98, 0.97, 0.96]):
        add_chunk(session, "catalogue", f"Product {i}", [score, 0.0])
    add_chunk(session, "sizing.md", "Sizing › Known issue", [0.95, 0.0])
    add_chunk(session, "faq.md", "FAQ › Fabric", [0.94, 0.0])
    session.commit()

    query = [1.0, 0.0]
    monkeypatch.setattr(
        rag, "get_query_embedder", lambda s: _async(FakeEmbedder({"tee sizing": query}))
    )

    hits = await rag.retrieve(session, "tee sizing", k=4, per_source=2)

    sources = [hit["source"] for hit in hits]
    assert sources.count("catalogue") == 2, "the cap should hold at two"
    assert "sizing.md" in sources, "the document that answers it must survive"


@pytest.mark.asyncio
async def test_the_cap_relaxes_when_there_is_nothing_else_to_pick(session, monkeypatch):
    """With only one source available, k should still be filled."""
    for i, score in enumerate([0.99, 0.98, 0.97, 0.96]):
        add_chunk(session, "catalogue", f"Product {i}", [score, 0.0])
    session.commit()

    monkeypatch.setattr(
        rag, "get_query_embedder", lambda s: _async(FakeEmbedder({"anything": [1.0, 0.0]}))
    )

    hits = await rag.retrieve(session, "anything", k=4, per_source=2)
    assert len(hits) == 4


@pytest.mark.asyncio
async def test_results_come_back_best_first(session, monkeypatch):
    add_chunk(session, "a.md", "worst", [0.10, 0.0])
    add_chunk(session, "b.md", "best", [0.99, 0.0])
    add_chunk(session, "c.md", "middle", [0.50, 0.0])
    session.commit()

    monkeypatch.setattr(
        rag, "get_query_embedder", lambda s: _async(FakeEmbedder({"q": [1.0, 0.0]}))
    )

    hits = await rag.retrieve(session, "q", k=3)
    assert [hit["title"] for hit in hits] == ["best", "middle", "worst"]


@pytest.mark.asyncio
async def test_an_empty_index_returns_nothing_rather_than_failing(session):
    assert await rag.retrieve(session, "anything") == []


def test_search_drops_results_below_the_floor():
    """A weak match is worse than no match — it gets cited as if it were real."""
    chunks = ["strong", "weak"]
    matrix = np.asarray([[1.0, 0.0], [0.01, 0.0]], dtype=np.float32)

    hits = vectorstore.search(np.asarray([1.0, 0.0]), chunks, matrix, k=2, min_score=0.05)

    assert [chunk for chunk, _ in hits] == ["strong"]


async def _async(value):
    """Wrap a value so it can stand in for an async function's result."""
    return value

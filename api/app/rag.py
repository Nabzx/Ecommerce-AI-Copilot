"""
Retrieval.

Turns the knowledge folder and the product catalogue into chunks, embeds them,
and finds the handful most relevant to a question. Every chunk keeps the file
and heading it came from, which is what lets the copilot cite its answer
instead of asserting things.

Build the index with:

    python -m app.rag
"""

import re
from pathlib import Path

import numpy as np
from sqlmodel import Session, delete, select

from app import vectorstore
from app.db import engine, create_tables
from app.models import Chunk, Product, Variant

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"

# Roughly a paragraph or two. Small enough to be a precise citation, big enough
# to still make sense when the model reads it on its own.
MAX_CHUNK_CHARS = 700


def split_markdown(text: str, source: str) -> list[tuple[str, str]]:
    """
    Split a markdown file into (title, text) pairs.

    Splits on ## headings first, since those are already the author's idea of
    where one topic ends. Anything still too long after that gets broken on
    paragraph boundaries rather than mid-sentence.
    """
    # The H1 is the document title; everything after is grouped by H2.
    document_title = source
    first_line = text.strip().split("\n", 1)[0]
    if first_line.startswith("# "):
        document_title = first_line[2:].strip()

    sections = re.split(r"^## ", text, flags=re.MULTILINE)
    chunks: list[tuple[str, str]] = []

    for section in sections:
        section = section.strip()
        if not section:
            continue

        lines = section.split("\n")
        heading = lines[0].strip().lstrip("# ").strip()
        body = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""

        # The first section is the H1 block, which often has no body worth keeping.
        if not body:
            continue

        title = f"{document_title} › {heading}" if heading != document_title else document_title

        if len(body) <= MAX_CHUNK_CHARS:
            chunks.append((title, body))
            continue

        # Too long — pack paragraphs together until the next one won't fit.
        current = ""
        for paragraph in body.split("\n\n"):
            if current and len(current) + len(paragraph) + 2 > MAX_CHUNK_CHARS:
                chunks.append((title, current.strip()))
                current = paragraph
            else:
                current = f"{current}\n\n{paragraph}" if current else paragraph
        if current.strip():
            chunks.append((title, current.strip()))

    return chunks


def collect_documents(session: Session) -> list[dict]:
    """Everything worth retrieving: the knowledge files and the catalogue."""
    documents: list[dict] = []

    # --- policy, FAQ, sizing ---
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        for title, text in split_markdown(path.read_text(), path.stem):
            documents.append({"source": path.name, "title": title, "text": text})

    # --- the catalogue ---
    # One chunk per product, written as a sentence rather than a row of fields,
    # because that's what the embedding model is good at reading.
    products = session.exec(select(Product).order_by(Product.title)).all()
    for product in products:
        variants = session.exec(select(Variant).where(Variant.product_id == product.id)).all()
        in_stock = [v.title for v in variants if v.inventory_quantity > 0]
        sold_out = [v.title for v in variants if v.inventory_quantity == 0]

        text = (
            f"{product.title} is a {product.product_type} priced at £{product.price:.2f}. "
            f"Tags: {product.tags.replace(',', ', ')}. "
            f"Sizes in stock: {', '.join(in_stock) if in_stock else 'none'}. "
            f"Sold out: {', '.join(sold_out) if sold_out else 'none'}. "
            f"Total units on hand: {sum(v.inventory_quantity for v in variants)}."
        )
        documents.append({"source": "catalogue", "title": product.title, "text": text})

    return documents


async def build_index() -> dict:
    """Re-chunk, re-embed and replace the whole index."""
    create_tables()

    with Session(engine) as session:
        documents = collect_documents(session)
        embedder = await vectorstore.resolve_embedder()

        texts = [doc["text"] for doc in documents]

        # The fallback has to see the corpus before it can embed anything.
        if isinstance(embedder, vectorstore.TfidfEmbedder):
            embedder.fit(texts)

        vectors = await embedder.embed(texts)

        session.exec(delete(Chunk))
        for doc, vector in zip(documents, vectors):
            session.add(
                Chunk(
                    source=doc["source"],
                    title=doc["title"],
                    text=doc["text"],
                    embedder=embedder.name,
                    dim=len(vector),
                    embedding=vectorstore.pack(vector),
                )
            )
        session.commit()

    return {"chunks": len(documents), "embedder": embedder.name}


async def get_query_embedder(session: Session):
    """
    Build an embedder that matches whatever created the stored index.

    Getting this wrong is the classic RAG bug — embedding the query with a
    different model to the documents gives you results that look ranked but
    are actually random.
    """
    stored = vectorstore.index_embedder_name(session)

    if stored == "tfidf":
        embedder = vectorstore.TfidfEmbedder()
        corpus = session.exec(select(Chunk.text)).all()
        embedder.fit(list(corpus))
        return embedder

    return vectorstore.ModelEmbedder()


async def retrieve(session: Session, query: str, k: int = 4) -> list[dict]:
    """The chunks most relevant to a question, best first."""
    chunks, matrix = vectorstore.load_matrix(session)
    if not chunks:
        return []

    embedder = await get_query_embedder(session)
    query_vector = (await embedder.embed([query]))[0]

    hits = vectorstore.search(np.asarray(query_vector), chunks, matrix, k=k)

    return [
        {
            "source": chunk.source,
            "title": chunk.title,
            "text": chunk.text,
            "score": round(score, 3),
        }
        for chunk, score in hits
    ]


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(build_index())
    print(f"indexed {result['chunks']} chunks using {result['embedder']}")

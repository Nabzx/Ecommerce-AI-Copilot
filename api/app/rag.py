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
from sqlmodel import Session, select

from app import vectorstore
from app.db import engine, create_tables
from app.models import Chunk, Product, Variant

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"

# Roughly a paragraph or two. Small enough to be a precise citation, big enough
# to still make sense when the model reads it on its own.
MAX_CHUNK_CHARS = 700

# What each kind of thing is actually made of. Taken straight from the FAQ, and
# it's what lets a search for "something light for summer" tell a 240gsm tee
# from a 400gsm hoodie — nothing else in the product data says how warm it is.
#
# The seasons are named and the word "warm" only appears on things that
# actually are. The tee used to read "breathable for warm weather", and that
# one word was enough to rank it above the hoodie for "warm layer for winter" —
# embeddings still carry plenty of straight lexical signal.
FABRIC = {
    "hoodie": "400gsm brushed-back cotton loopback. Heavyweight and warm, for autumn and winter.",
    "crewneck": "400gsm brushed-back cotton. Heavyweight and warm, for autumn and winter.",
    "tee": "240gsm combed cotton. Lightweight and breathable, for summer and hot days.",
    "longsleeve": "240gsm combed cotton. Midweight layer for spring and autumn.",
    "trouser": "Cotton ripstop. Midweight, worn all year round.",
    "short": "Cotton ripstop. Lightweight, for summer and hot days.",
    "outerwear": "Insulated and heavyweight. The warmest layer, for deep winter and cold days.",
    "accessory": "Knitted. Worn through autumn and winter.",
}


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

    # --- parse into (heading, body) ---
    sections: list[tuple[str, str]] = []
    for section in re.split(r"^## ", text, flags=re.MULTILINE):
        section = section.strip()
        if not section:
            continue
        lines = section.split("\n")
        heading = lines[0].strip().lstrip("# ").strip()
        body = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
        # The first block is the H1, which usually has no body worth keeping.
        if body:
            sections.append((heading, body))

    chunks: list[tuple[str, str]] = []
    buffer: list[tuple[str, str]] = []

    def flush() -> None:
        """Turn whatever has accumulated into one chunk."""
        if not buffer:
            return
        headings = ", ".join(heading for heading, _ in buffer)
        body = "\n\n".join(f"{heading}\n{text}" for heading, text in buffer)
        chunks.append((f"{document_title} › {headings}", body))
        buffer.clear()

    for heading, body in sections:
        # A long section stands on its own, split on paragraph boundaries.
        if len(body) > MAX_CHUNK_CHARS:
            flush()
            title = f"{document_title} › {heading}"
            current = ""
            for paragraph in body.split("\n\n"):
                if current and len(current) + len(paragraph) + 2 > MAX_CHUNK_CHARS:
                    chunks.append((title, current.strip()))
                    current = paragraph
                else:
                    current = f"{current}\n\n{paragraph}" if current else paragraph
            if current.strip():
                chunks.append((title, current.strip()))
            continue

        # Short sections get merged with their neighbours. Splitting on every
        # heading leaves fragments like "Shipping › Europe" too thin to rank —
        # they lose the surrounding delivery language that makes them findable.
        pending = sum(len(b) for _, b in buffer) + len(body)
        if buffer and pending > MAX_CHUNK_CHARS:
            flush()
        buffer.append((heading, body))

    flush()
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

        # What the copilot reads, so it can answer "is the hoodie in stock?".
        text = (
            f"{product.title} is a {product.product_type} priced at £{product.price:.2f}. "
            f"{FABRIC.get(product.product_type, '')} "
            f"Tags: {product.tags.replace(',', ', ')}. "
            f"Sizes in stock: {', '.join(in_stock) if in_stock else 'none'}. "
            f"Sold out: {', '.join(sold_out) if sold_out else 'none'}. "
            f"Total units on hand: {sum(v.inventory_quantity for v in variants)}."
        )

        # What gets embedded, which is deliberately not the same thing. The
        # stock lines are near identical on every product, and including them
        # pulled all fourteen vectors together — "something light for summer"
        # was returning the puffer vest first. Describing only the garment
        # keeps the differences that matter.
        embed_text = (
            f"{product.title}. A {product.product_type}. "
            f"{FABRIC.get(product.product_type, '')} "
            f"Tags: {product.tags.replace(',', ', ')}. Priced at £{product.price:.2f}."
        )

        documents.append(
            {
                "source": "catalogue",
                "title": product.title,
                "text": text,
                "embed_text": embed_text,
                "ref_id": product.id,
            }
        )

    return documents


async def build_index() -> dict:
    """Re-chunk, re-embed and replace the whole index."""
    create_tables()

    with Session(engine) as session:
        documents = collect_documents(session)
        embedder = await vectorstore.resolve_embedder()

        # Embed the heading along with the body. Without it a section like
        # "Sizing › Known issue" loses the word "sizing" entirely, and a
        # question about sizing then ranks below every product in the
        # catalogue that happens to share a word with the query.
        # Products supply their own embed_text; documents fall back to the body.
        texts = [doc.get("embed_text") or f"{doc['title']}\n{doc['text']}" for doc in documents]

        # The fallback has to see the corpus before it can embed anything.
        if isinstance(embedder, vectorstore.TfidfEmbedder):
            embedder.fit(texts)

        vectors = await embedder.embed(texts)

        # Drop and recreate rather than delete the rows. The index is derived
        # data that can always be rebuilt, so when a column gets added to
        # Chunk this picks it up instead of failing against the old table —
        # which saves carrying a migration tool for a cache.
        Chunk.__table__.drop(engine, checkfirst=True)
        Chunk.__table__.create(engine)

        for doc, vector in zip(documents, vectors):
            session.add(
                Chunk(
                    source=doc["source"],
                    title=doc["title"],
                    text=doc["text"],
                    ref_id=doc.get("ref_id"),
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


async def retrieve(session: Session, query: str, k: int = 4, per_source: int = 2) -> list[dict]:
    """
    The chunks most relevant to a question, best first.

    Results are capped per source. There are fourteen products in the
    catalogue and only a handful of policy sections, so without a cap a
    question like "does the tee run small?" fills every slot with near
    identical product entries and pushes the sizing doc — the one thing that
    actually answers it — off the end of the list.

    The cap is relaxed at the end if there weren't enough sources to fill k.
    """
    chunks, matrix = vectorstore.load_matrix(session)
    if not chunks:
        return []

    embedder = await get_query_embedder(session)
    query_vector = (await embedder.embed([query], kind="query"))[0]

    # Pull a wider candidate list so there's something to diversify over.
    hits = vectorstore.search(np.asarray(query_vector), chunks, matrix, k=k * 4)

    selected: list[tuple[Chunk, float]] = []
    per_source_count: dict[str, int] = {}

    for chunk, score in hits:
        if per_source_count.get(chunk.source, 0) >= per_source:
            continue
        selected.append((chunk, score))
        per_source_count[chunk.source] = per_source_count.get(chunk.source, 0) + 1
        if len(selected) == k:
            break

    # Not enough variety to fill k — take the next best regardless of source.
    if len(selected) < k:
        chosen = {id(chunk) for chunk, _ in selected}
        for chunk, score in hits:
            if id(chunk) in chosen:
                continue
            selected.append((chunk, score))
            if len(selected) == k:
                break

    return [
        {
            "source": chunk.source,
            "title": chunk.title,
            "text": chunk.text,
            "score": round(score, 3),
        }
        for chunk, score in selected
    ]


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(build_index())
    print(f"indexed {result['chunks']} chunks using {result['embedder']}")

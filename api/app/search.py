"""
Semantic product search.

"cozy autumn pieces" should find the beanie and the puffer vest even though
neither word appears anywhere in either product. That works because the same
embeddings the copilot retrieves over already cover the catalogue — this file
is mostly about filtering to the catalogue chunks and getting back to a real
product row.
"""

import numpy as np
from sqlmodel import Session, select

from app import rag, vectorstore
from app.models import Chunk, Product, Variant


async def search_products(session: Session, query: str, limit: int = 6) -> list[dict]:
    """Products most like the query, best first."""
    chunks = session.exec(select(Chunk).where(Chunk.source == "catalogue")).all()
    if not chunks:
        return []

    matrix = np.vstack([vectorstore.unpack(chunk.embedding) for chunk in chunks])

    # Has to be the same embedder that built the index, or the ranking is
    # meaningless — see the note in rag.get_query_embedder.
    embedder = await rag.get_query_embedder(session)
    query_vector = np.asarray((await embedder.embed([query], kind="query"))[0])

    hits = vectorstore.search(query_vector, list(chunks), matrix, k=limit, min_score=0.15)

    results = []
    for chunk, score in hits:
        if chunk.ref_id is None:
            continue
        product = session.get(Product, chunk.ref_id)
        if not product:
            continue

        variants = session.exec(select(Variant).where(Variant.product_id == product.id)).all()
        in_stock = [v.title for v in variants if v.inventory_quantity > 0]

        results.append(
            {
                "product_id": product.id,
                "title": product.title,
                "product_type": product.product_type,
                "price": product.price,
                "tags": [t for t in product.tags.split(",") if t],
                "sizes_in_stock": in_stock,
                "units_in_stock": sum(v.inventory_quantity for v in variants),
                "score": round(score, 3),
            }
        )

    return results

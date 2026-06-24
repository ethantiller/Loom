import numpy as np
import pytest

from app.ingestion.embedder import embed, embed_query


QUERY = "Which planet is known as the Red Planet?"
DOCUMENTS = [
    "Venus is often called Earth's twin because of its similar size and proximity.",
    "Mars, known for its reddish appearance, is often referred to as the Red Planet.",
    "Jupiter, the largest planet in our solar system, has a prominent red spot.",
    "Saturn, famous for its rings, is sometimes mistaken for the Red Planet.",
]
MARS_IDX = 1


@pytest.fixture(scope="module")
def embeddings():
    doc_vecs = embed(DOCUMENTS)
    query_vec = embed_query(QUERY)
    return doc_vecs, query_vec


def test_embed_output_shape(embeddings):
    doc_vecs, _ = embeddings
    assert doc_vecs.shape == (len(DOCUMENTS), 768)


def test_embed_query_output_shape(embeddings):
    _, query_vec = embeddings
    assert query_vec.shape == (768,)


def test_embeddings_are_normalized(embeddings):
    doc_vecs, query_vec = embeddings
    norms = np.linalg.norm(doc_vecs, axis=1)
    np.testing.assert_allclose(norms, 1.0, atol=1e-5)
    np.testing.assert_allclose(np.linalg.norm(query_vec), 1.0, atol=1e-5)


def test_mars_document_ranks_highest(embeddings):
    doc_vecs, query_vec = embeddings
    similarities = doc_vecs @ query_vec
    assert similarities.argmax() == MARS_IDX, (
        f"Expected Mars doc (idx {MARS_IDX}) to rank highest, "
        f"got idx {similarities.argmax()} — similarities: {similarities}"
    )

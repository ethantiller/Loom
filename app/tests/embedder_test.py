from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ingestion.embedder import embed, embed_query

query = "Which planet is known as the Red Planet?"
documents = [
    "Venus is often called Earth's twin because of its similar size and proximity.",
    "Mars, known for its reddish appearance, is often referred to as the Red Planet.",
    "Jupiter, the largest planet in our solar system, has a prominent red spot.",
    "Saturn, famous for its rings, is sometimes mistaken for the Red Planet.",
]

query_vec = embed_query(query)     
doc_vecs = embed(documents)     

similarities = doc_vecs @ query_vec
print(similarities)
# Gemini specifically mentioned that the above query should yield:
# per the official model card: ~[0.3011, 0.6359, 0.4930, 0.4889]
# So check if similarities is close to that

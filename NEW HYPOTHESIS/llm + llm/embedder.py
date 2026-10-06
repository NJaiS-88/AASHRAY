from typing import List, Union
import numpy as np
from sentence_transformers import SentenceTransformer

class Embedder:
    _instance = None

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5", device: str = "cpu"):
        self.model_name = model_name
        self.device = device
        self.model = SentenceTransformer(model_name, device=device)
        self.dimension = self.model.get_sentence_embedding_dimension()

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of strings into normalized vectors."""
        if not texts:
            return []
        embeddings = self.model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True
        )
        return embeddings.tolist()

    def embed_query(self, query: str) -> List[float]:
        """Embed a single query text."""
        return self.embed_texts([query])[0]

"""
Vector Store Service - Store and search embeddings
Uses Redis for storage with Python-based similarity search
(Can be upgraded to Redis Stack/RediSearch for native vector search)
"""
import redis
import json
import numpy as np
from typing import List, Dict, Optional, Tuple
import os


class VectorStore:
    """
    Store and search document embeddings using Redis

    Storage format:
        kb:vector:{doc_id} → JSON with {embedding, metadata}
        kb:index:all → Set of all doc_ids
    """

    def __init__(self, redis_url: Optional[str] = None):
        """
        Initialize vector store

        Args:
            redis_url: Redis connection URL (default: from REDIS_URL env var)
        """
        redis_url = redis_url or os.getenv('REDIS_URL', 'redis://localhost:6379/0')
        self.redis = redis.from_url(redis_url, decode_responses=False)
        self.index_key = 'kb:index:all'

    def _vector_key(self, doc_id: str) -> str:
        """Generate Redis key for document vector"""
        return f"kb:vector:{doc_id}"

    def _metadata_key(self, doc_id: str) -> str:
        """Generate Redis key for document metadata"""
        return f"kb:metadata:{doc_id}"

    def store_vector(
        self,
        doc_id: str,
        embedding: List[float],
        metadata: Optional[Dict] = None
    ):
        """
        Store a document embedding with metadata

        Args:
            doc_id: Unique document identifier
            embedding: Embedding vector as list of floats
            metadata: Optional metadata (source, title, date, etc.)
        """
        # Convert embedding to numpy array for efficient storage
        vector_bytes = np.array(embedding, dtype=np.float32).tobytes()

        # Store vector
        self.redis.set(self._vector_key(doc_id), vector_bytes)

        # Store metadata as JSON
        if metadata:
            self.redis.set(
                self._metadata_key(doc_id),
                json.dumps(metadata)
            )

        # Add to index
        self.redis.sadd(self.index_key, doc_id)

    def get_vector(self, doc_id: str) -> Optional[np.ndarray]:
        """Retrieve embedding vector for a document"""
        vector_bytes = self.redis.get(self._vector_key(doc_id))
        if vector_bytes:
            return np.frombuffer(vector_bytes, dtype=np.float32)
        return None

    def get_metadata(self, doc_id: str) -> Optional[Dict]:
        """Retrieve metadata for a document"""
        metadata_json = self.redis.get(self._metadata_key(doc_id))
        if metadata_json:
            return json.loads(metadata_json)
        return None

    def delete_vector(self, doc_id: str):
        """Delete a document and its metadata"""
        self.redis.delete(self._vector_key(doc_id))
        self.redis.delete(self._metadata_key(doc_id))
        self.redis.srem(self.index_key, doc_id)

    def get_all_doc_ids(self) -> List[str]:
        """Get all document IDs in the store"""
        doc_ids = self.redis.smembers(self.index_key)
        return [doc_id.decode('utf-8') for doc_id in doc_ids]

    def count_vectors(self) -> int:
        """Count total number of vectors stored"""
        return self.redis.scard(self.index_key)

    def cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Calculate cosine similarity between two vectors"""
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        filters: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Search for similar documents using cosine similarity

        Args:
            query_embedding: Query vector
            top_k: Number of results to return
            filters: Optional metadata filters (e.g., {'source': 'gmail'})

        Returns:
            List of dicts with doc_id, score, metadata
        """
        query_vector = np.array(query_embedding, dtype=np.float32)

        # Get all document IDs
        all_doc_ids = self.get_all_doc_ids()

        if not all_doc_ids:
            return []

        # Calculate similarity for each document
        similarities = []

        for doc_id in all_doc_ids:
            # Get vector
            doc_vector = self.get_vector(doc_id)
            if doc_vector is None:
                continue

            # Get metadata
            metadata = self.get_metadata(doc_id)

            # Apply filters
            if filters and metadata:
                skip = False
                for key, value in filters.items():
                    if metadata.get(key) != value:
                        skip = True
                        break
                if skip:
                    continue

            # Calculate similarity
            similarity = self.cosine_similarity(query_vector, doc_vector)

            similarities.append({
                'doc_id': doc_id,
                'score': float(similarity),
                'metadata': metadata or {}
            })

        # Sort by similarity (descending)
        similarities.sort(key=lambda x: x['score'], reverse=True)

        # Return top_k results
        return similarities[:top_k]

    def clear_all(self):
        """Clear all vectors and metadata (use with caution!)"""
        all_doc_ids = self.get_all_doc_ids()

        for doc_id in all_doc_ids:
            self.delete_vector(doc_id)

        # Clear index
        self.redis.delete(self.index_key)

    def get_stats(self) -> Dict:
        """Get statistics about the vector store"""
        all_doc_ids = self.get_all_doc_ids()

        if not all_doc_ids:
            return {
                'total_vectors': 0,
                'sources': {},
                'sample_metadata': None
            }

        # Count by source
        sources = {}
        sample_metadata = None

        for doc_id in all_doc_ids:
            metadata = self.get_metadata(doc_id)
            if metadata:
                source = metadata.get('source', 'unknown')
                sources[source] = sources.get(source, 0) + 1

                if sample_metadata is None:
                    sample_metadata = metadata

        return {
            'total_vectors': len(all_doc_ids),
            'sources': sources,
            'sample_metadata': sample_metadata
        }


if __name__ == '__main__':
    # Test vector store
    import sys

    print("Testing Vector Store...")

    store = VectorStore()

    # Test storing vectors
    test_docs = [
        {
            'id': 'doc1',
            'embedding': [0.1, 0.2, 0.3, 0.4],
            'metadata': {'source': 'gmail', 'subject': 'Test email 1'}
        },
        {
            'id': 'doc2',
            'embedding': [0.15, 0.25, 0.28, 0.42],
            'metadata': {'source': 'gmail', 'subject': 'Test email 2'}
        },
        {
            'id': 'doc3',
            'embedding': [0.9, 0.1, 0.05, 0.01],
            'metadata': {'source': 'teams', 'subject': 'Teams message'}
        }
    ]

    print("\nStoring test vectors...")
    for doc in test_docs:
        store.store_vector(doc['id'], doc['embedding'], doc['metadata'])

    print(f"Stored {store.count_vectors()} vectors")

    # Test search
    print("\nSearching for similar documents...")
    query = [0.12, 0.22, 0.31, 0.39]  # Similar to doc1 and doc2

    results = store.search(query, top_k=3)

    print("Search results:")
    for i, result in enumerate(results, 1):
        print(f"  {i}. {result['doc_id']} (score: {result['score']:.4f})")
        print(f"     Metadata: {result['metadata']}")

    # Test filters
    print("\nSearching with filter (source=gmail)...")
    results = store.search(query, top_k=3, filters={'source': 'gmail'})

    print("Filtered results:")
    for i, result in enumerate(results, 1):
        print(f"  {i}. {result['doc_id']} (score: {result['score']:.4f})")

    # Stats
    print("\nVector store stats:")
    stats = store.get_stats()
    print(json.dumps(stats, indent=2))

    # Cleanup
    print("\nCleaning up test data...")
    for doc in test_docs:
        store.delete_vector(doc['id'])

    print("✓ Test complete")

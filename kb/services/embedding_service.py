"""
Embedding Service - Generate embeddings for semantic search
Supports OpenAI and Anthropic embedding models
"""
import os
from typing import List, Dict, Optional
import hashlib
import json
from pathlib import Path


class EmbeddingService:
    """Generate and cache embeddings for text documents"""

    def __init__(self, provider: str = 'voyage', cache_dir: str = '/var/www/astrogen/kb_data/embeddings'):
        """
        Initialize embedding service

        Args:
            provider: 'openai', 'voyage', or 'sentence-transformers'
            cache_dir: Directory to cache embeddings (optional)
        """
        self.provider = provider
        self.cache_dir = Path(cache_dir) if cache_dir else None

        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        if provider == 'openai':
            self._init_openai()
        elif provider == 'voyage':
            self._init_voyage()
        elif provider == 'sentence-transformers':
            self._init_sentence_transformers()
        else:
            raise ValueError(f"Unsupported provider: {provider}. Use 'openai', 'voyage', or 'sentence-transformers'")

    def _init_openai(self):
        """Initialize OpenAI client"""
        try:
            from openai import OpenAI
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")

            self.client = OpenAI(api_key=api_key)
            self.model = 'text-embedding-3-small'  # 1536 dimensions, cheap, fast
            self.dimensions = 1536

        except ImportError:
            raise ImportError("OpenAI library not installed. Run: pip install openai")

    def _init_voyage(self):
        """Initialize Voyage AI client (Anthropic's recommended embedding provider)"""
        try:
            import voyageai
            api_key = os.getenv('VOYAGE_API_KEY')
            if not api_key:
                raise ValueError(
                    "VOYAGE_API_KEY environment variable not set.\n"
                    "Get your key at: https://dash.voyageai.com/\n"
                    "Voyage AI is free tier: 100M tokens/month"
                )

            self.client = voyageai.Client(api_key=api_key)
            self.model = 'voyage-2'  # 1024 dimensions, optimized for general purpose
            self.dimensions = 1024

        except ImportError:
            raise ImportError(
                "Voyage AI library not installed.\n"
                "Run: pip install voyageai"
            )

    def _init_sentence_transformers(self):
        """Initialize Sentence Transformers (local, free, no API needed)"""
        try:
            from sentence_transformers import SentenceTransformer

            print("Loading local embedding model (first time may take a few minutes)...")
            # Use smaller model to save memory (~61MB instead of 384MB)
            # Trade-off: slightly lower quality but 6x less memory
            self.client = SentenceTransformer('paraphrase-MiniLM-L3-v2')
            self.model = 'paraphrase-MiniLM-L3-v2'
            self.dimensions = 384  # This model outputs 384-dimensional vectors
            print("✓ Model loaded successfully (lightweight version)")

        except ImportError:
            raise ImportError(
                "Sentence Transformers library not installed.\n"
                "Run: pip install sentence-transformers"
            )

    def _get_cache_key(self, text: str) -> str:
        """Generate cache key from text hash"""
        text_hash = hashlib.md5(text.encode()).hexdigest()
        return f"{self.provider}_{self.model}_{text_hash}"

    def _load_from_cache(self, cache_key: str) -> Optional[List[float]]:
        """Load embedding from cache if exists"""
        if not self.cache_dir:
            return None

        cache_file = self.cache_dir / f"{cache_key}.json"
        if cache_file.exists():
            with open(cache_file, 'r') as f:
                data = json.load(f)
                return data['embedding']
        return None

    def _save_to_cache(self, cache_key: str, embedding: List[float]):
        """Save embedding to cache"""
        if not self.cache_dir:
            return

        cache_file = self.cache_dir / f"{cache_key}.json"
        with open(cache_file, 'w') as f:
            json.dump({
                'embedding': embedding,
                'provider': self.provider,
                'model': self.model,
                'dimensions': len(embedding)
            }, f)

    def embed(self, text: str, use_cache: bool = True) -> List[float]:
        """
        Generate embedding for a single text

        Args:
            text: Text to embed
            use_cache: Whether to use cached embeddings

        Returns:
            List of floats representing the embedding vector
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        # Check cache
        if use_cache:
            cache_key = self._get_cache_key(text)
            cached = self._load_from_cache(cache_key)
            if cached:
                return cached

        # Generate embedding
        if self.provider == 'openai':
            embedding = self._embed_openai(text)
        elif self.provider == 'voyage':
            embedding = self._embed_voyage(text)
        elif self.provider == 'sentence-transformers':
            embedding = self._embed_sentence_transformers(text)
        else:
            raise NotImplementedError(f"Provider {self.provider} not implemented")

        # Save to cache
        if use_cache:
            self._save_to_cache(cache_key, embedding)

        return embedding

    def _embed_openai(self, text: str) -> List[float]:
        """Generate embedding using OpenAI API"""
        # Truncate text if too long (OpenAI limit: ~8191 tokens for text-embedding-3-small)
        # Rough estimate: 1 token ≈ 4 characters
        max_chars = 8191 * 4
        if len(text) > max_chars:
            text = text[:max_chars]

        response = self.client.embeddings.create(
            model=self.model,
            input=text
        )

        return response.data[0].embedding

    def _embed_voyage(self, text: str) -> List[float]:
        """Generate embedding using Voyage AI API"""
        # Voyage has similar limits to OpenAI
        max_chars = 8000 * 4
        if len(text) > max_chars:
            text = text[:max_chars]

        result = self.client.embed(
            texts=[text],
            model=self.model,
            input_type='document'  # 'document' for indexing, 'query' for searching
        )

        return result.embeddings[0]

    def _embed_sentence_transformers(self, text: str) -> List[float]:
        """Generate embedding using local Sentence Transformers model (no API needed!)"""
        # This runs locally on CPU/GPU, completely free
        embedding = self.client.encode(text, convert_to_numpy=True)
        return embedding.tolist()

    def embed_batch(self, texts: List[str], use_cache: bool = True) -> List[List[float]]:
        """
        Generate embeddings for multiple texts (batch processing)

        Args:
            texts: List of texts to embed
            use_cache: Whether to use cached embeddings

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        embeddings = []

        for text in texts:
            embedding = self.embed(text, use_cache=use_cache)
            embeddings.append(embedding)

        return embeddings

    def embed_document(
        self,
        document_id: str,
        text: str,
        chunk_size: int = 500,
        overlap: int = 50,
        use_cache: bool = True
    ) -> List[Dict]:
        """
        Embed a document by chunking it into smaller pieces

        Args:
            document_id: Unique identifier for the document
            text: Full document text
            chunk_size: Approximate number of words per chunk
            overlap: Number of overlapping words between chunks
            use_cache: Whether to use cached embeddings

        Returns:
            List of dicts with chunk_index, chunk_text, embedding
        """
        # Split into words
        words = text.split()

        chunks = []
        chunk_index = 0

        for i in range(0, len(words), chunk_size - overlap):
            chunk_words = words[i:i + chunk_size]
            chunk_text = ' '.join(chunk_words)

            if chunk_text.strip():
                embedding = self.embed(chunk_text, use_cache=use_cache)

                chunks.append({
                    'document_id': document_id,
                    'chunk_index': chunk_index,
                    'chunk_text': chunk_text,
                    'embedding': embedding,
                    'token_count': len(chunk_words)
                })

                chunk_index += 1

        return chunks

    def get_embedding_dimensions(self) -> int:
        """Get dimensionality of embedding vectors"""
        return self.dimensions


if __name__ == '__main__':
    # Test embedding service
    import sys

    if not os.getenv('OPENAI_API_KEY'):
        print("Error: OPENAI_API_KEY not set")
        sys.exit(1)

    service = EmbeddingService(provider='openai')

    test_text = "This is a test email about variable stars and astronomical observations."
    print(f"Test text: {test_text}")

    embedding = service.embed(test_text)
    print(f"Embedding dimensions: {len(embedding)}")
    print(f"First 10 values: {embedding[:10]}")

    # Test chunking
    long_text = " ".join([test_text] * 100)
    chunks = service.embed_document('test_doc', long_text, chunk_size=50, overlap=10)
    print(f"\nDocument chunking test:")
    print(f"  Original length: {len(long_text.split())} words")
    print(f"  Number of chunks: {len(chunks)}")
    print(f"  Chunk 0 length: {chunks[0]['token_count']} words")

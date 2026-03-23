"""
Base Document Parser - Abstract interface for all document types
"""

import json
import hashlib
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class BaseDocumentParser(ABC):
    """Abstract base class for document parsers"""

    def __init__(self, output_dir: str = '/var/www/astrogen/kb_data/documents_parsed'):
        """
        Initialize parser with output directory

        Args:
            output_dir: Directory to store parsed JSON files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.output_dir / 'index.json'
        self.parser_type = self.__class__.__name__

    @abstractmethod
    def parse(self, file_path: str, **kwargs) -> Dict:
        """
        Parse document and return standardized JSON structure

        Args:
            file_path: Path to file to parse
            **kwargs: Additional parser-specific arguments (tags, metadata, etc.)

        Returns:
            Dictionary with standardized document format:
            {
                'id': 'unique_hash',
                'doc_type': 'text|markdown|email',
                'title': 'Document title',
                'date': 'ISO8601 timestamp',
                'tags': ['tag1', 'tag2'],
                'content': 'Full text content',
                'content_length': 1234,
                'source': '/path/to/file',
                'metadata': {...parser-specific fields...},
                'indexed_at': 'ISO8601 timestamp'
            }
        """
        raise NotImplementedError

    @staticmethod
    def _generate_id(file_path: str, content_hash: Optional[str] = None) -> str:
        """
        Generate unique document ID using MD5 hash

        Args:
            file_path: Path to file
            content_hash: Optional content hash for additional uniqueness

        Returns:
            MD5 hash as unique ID
        """
        path = Path(file_path)
        if content_hash:
            hash_input = f"{path.name}{content_hash}".encode()
        else:
            hash_input = f"{path.name}{path.stat().st_mtime}".encode()

        return hashlib.md5(hash_input).hexdigest()

    def _save_document(self, doc_data: Dict, doc_id: str) -> Path:
        """
        Save document JSON to disk

        Args:
            doc_data: Document dictionary
            doc_id: Document ID (filename without extension)

        Returns:
            Path to saved file
        """
        output_file = self.output_dir / f"{doc_id}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(doc_data, f, indent=2, ensure_ascii=False)
        return output_file

    def _update_index(self, doc_id: str, doc_data: Dict) -> None:
        """
        Update index file with document metadata

        Args:
            doc_id: Document ID
            doc_data: Document dictionary
        """
        # Load existing index or create new
        if self.index_file.exists():
            with open(self.index_file, 'r', encoding='utf-8') as f:
                index = json.load(f)
        else:
            index = {'documents': {}, 'metadata': {}}

        # Add/update document entry
        index['documents'][doc_id] = {
            'title': doc_data.get('title'),
            'doc_type': doc_data.get('doc_type'),
            'date': doc_data.get('date'),
            'tags': doc_data.get('tags', []),
            'source': doc_data.get('source'),
            'content_length': doc_data.get('content_length'),
            'file_path': str(self.output_dir / f"{doc_id}.json"),
            'indexed_at': doc_data.get('indexed_at')
        }

        # Update metadata
        if 'total_documents' not in index['metadata']:
            index['metadata']['total_documents'] = 0

        index['metadata']['total_documents'] = len(index['documents'])
        index['metadata']['last_updated'] = datetime.now().isoformat()

        # Save updated index
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2, ensure_ascii=False)

    def _build_document(
        self,
        doc_id: str,
        title: str,
        content: str,
        tags: List[str],
        source: str,
        date: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Dict:
        """
        Build standardized document dictionary

        Args:
            doc_id: Unique document ID
            title: Document title
            content: Full text content
            tags: List of tags
            source: Source file path
            date: ISO8601 date (defaults to now)
            metadata: Parser-specific metadata

        Returns:
            Standardized document dictionary
        """
        if date is None:
            date = datetime.now().isoformat()

        return {
            'id': doc_id,
            'doc_type': self._infer_doc_type(),
            'title': title,
            'date': date,
            'tags': tags or [],
            'content': content,
            'content_length': len(content),
            'source': source,
            'metadata': metadata or {},
            'indexed_at': datetime.now().isoformat()
        }

    def _infer_doc_type(self) -> str:
        """Infer document type from parser class name"""
        class_name = self.__class__.__name__
        if 'Text' in class_name:
            return 'text'
        elif 'Markdown' in class_name:
            return 'markdown'
        elif 'PDF' in class_name:
            return 'pdf'
        else:
            return 'document'

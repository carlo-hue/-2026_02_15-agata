"""
Text File Parser - Parse plain text files (.txt)
"""

from pathlib import Path
from typing import List, Optional
from .base_parser import BaseDocumentParser


class TextFileParserService(BaseDocumentParser):
    """Parser for plain text files"""

    def parse(
        self,
        file_path: str,
        tags: Optional[List[str]] = None,
        title: Optional[str] = None
    ) -> dict:
        """
        Parse plain text file

        Args:
            file_path: Path to .txt file
            tags: Optional list of tags to add
            title: Optional document title (defaults to filename)

        Returns:
            Standardized document dictionary
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not path.is_file():
            raise ValueError(f"Not a file: {file_path}")

        # Read content
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            # Fallback to latin-1
            with open(path, 'r', encoding='latin-1') as f:
                content = f.read()

        # Generate document ID
        doc_id = self._generate_id(str(path))

        # Use provided title or derive from filename
        if title is None:
            title = path.stem  # Filename without extension

        # Get file metadata
        file_stat = path.stat()

        # Build document
        doc_data = self._build_document(
            doc_id=doc_id,
            title=title,
            content=content,
            tags=tags or [],
            source=str(path.absolute()),
            metadata={
                'file_path': str(path),
                'file_size': file_stat.st_size,
                'file_extension': path.suffix,
            }
        )

        # Save to disk
        self._save_document(doc_data, doc_id)

        # Update index
        self._update_index(doc_id, doc_data)

        return doc_data

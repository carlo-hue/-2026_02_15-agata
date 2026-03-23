"""
Markdown File Parser - Parse markdown files with frontmatter support
"""

import re
from pathlib import Path
from datetime import datetime
from typing import List, Optional

try:
    import frontmatter
except ImportError:
    frontmatter = None

from .base_parser import BaseDocumentParser


class MarkdownParserService(BaseDocumentParser):
    """Parser for markdown files with optional frontmatter"""

    def parse(
        self,
        file_path: str,
        tags: Optional[List[str]] = None,
        **kwargs
    ) -> dict:
        """
        Parse markdown file with frontmatter support

        Frontmatter example:
        ---
        title: My Document
        tags: [tag1, tag2]
        date: 2026-02-02
        ---

        # Content starts here

        Args:
            file_path: Path to .md file
            tags: Optional list of tags to add to frontmatter tags
            **kwargs: Additional metadata to merge

        Returns:
            Standardized document dictionary
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not path.is_file():
            raise ValueError(f"Not a file: {file_path}")

        # Read and parse file
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(path, 'r', encoding='latin-1') as f:
                content = f.read()

        # Parse frontmatter if available
        if frontmatter:
            post = frontmatter.loads(content)
            metadata_dict = dict(post.metadata)
            body_text = post.content
        else:
            # Fallback: simple frontmatter parsing (YAML-like)
            metadata_dict, body_text = self._parse_simple_frontmatter(content)

        # Generate document ID
        doc_id = self._generate_id(str(path))

        # Extract or build title
        title = metadata_dict.get('title')
        if not title:
            # Try to extract from first H1
            h1_match = re.match(r'^#\s+(.+)$', body_text, re.MULTILINE)
            if h1_match:
                title = h1_match.group(1)
            else:
                title = path.stem

        # Merge tags
        fm_tags = metadata_dict.get('tags', [])
        if isinstance(fm_tags, str):
            fm_tags = [fm_tags]
        all_tags = list(set((tags or []) + fm_tags))

        # Extract date
        date_str = metadata_dict.get('date')
        if date_str:
            try:
                # Try to parse ISO format
                if isinstance(date_str, str):
                    dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    date_str = dt.isoformat()
            except (ValueError, AttributeError):
                pass  # Keep original format
        else:
            date_str = datetime.now().isoformat()

        # Convert markdown to plain text (strip HTML formatting)
        plain_text = self._markdown_to_text(body_text)

        # Get file metadata
        file_stat = path.stat()

        # Build metadata
        doc_metadata = {
            'file_path': str(path),
            'file_size': file_stat.st_size,
            'file_extension': path.suffix,
            'frontmatter': metadata_dict,
            'has_code_blocks': '```' in body_text,
        }
        doc_metadata.update(kwargs)

        # Build document
        doc_data = self._build_document(
            doc_id=doc_id,
            title=title,
            content=plain_text,
            tags=all_tags,
            source=str(path.absolute()),
            date=date_str,
            metadata=doc_metadata
        )

        # Save to disk
        self._save_document(doc_data, doc_id)

        # Update index
        self._update_index(doc_id, doc_data)

        return doc_data

    @staticmethod
    def _parse_simple_frontmatter(content: str) -> tuple:
        """
        Simple YAML-like frontmatter parser for when python-frontmatter is not available

        Returns:
            (metadata_dict, body_text) tuple
        """
        lines = content.split('\n')

        # Check for frontmatter delimiters
        if len(lines) > 0 and lines[0].strip() == '---':
            # Find closing delimiter
            end_idx = None
            for i in range(1, len(lines)):
                if lines[i].strip() == '---':
                    end_idx = i
                    break

            if end_idx:
                # Parse YAML-like metadata
                metadata_lines = lines[1:end_idx]
                metadata_dict = {}

                for line in metadata_lines:
                    if ':' in line:
                        key, value = line.split(':', 1)
                        key = key.strip()
                        value = value.strip()

                        # Handle arrays [tag1, tag2]
                        if value.startswith('[') and value.endswith(']'):
                            value = [v.strip() for v in value[1:-1].split(',')]
                        elif value.lower() in ('true', 'false'):
                            value = value.lower() == 'true'

                        metadata_dict[key] = value

                body_text = '\n'.join(lines[end_idx + 1:])
                return metadata_dict, body_text

        # No frontmatter found
        return {}, content

    @staticmethod
    def _markdown_to_text(markdown_text: str) -> str:
        """
        Convert markdown to plain text by removing markdown syntax

        Args:
            markdown_text: Markdown formatted text

        Returns:
            Plain text with minimal formatting
        """
        text = markdown_text

        # Remove code blocks (preserve content)
        text = re.sub(r'```[\s\S]*?```', '', text)
        text = re.sub(r'`[^`]+`', '', text)

        # Remove inline links but keep text
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)

        # Remove markdown headers but keep text
        text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)

        # Remove bold/italic
        text = re.sub(r'\*\*([^\*]+)\*\*', r'\1', text)
        text = re.sub(r'__([^_]+)__', r'\1', text)
        text = re.sub(r'\*([^\*]+)\*', r'\1', text)
        text = re.sub(r'_([^_]+)_', r'\1', text)

        # Remove horizontal rules
        text = re.sub(r'^---+\s*$', '', text, flags=re.MULTILINE)

        # Remove list markers
        text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)

        # Clean up multiple newlines
        text = re.sub(r'\n{3,}', '\n\n', text)

        return text.strip()

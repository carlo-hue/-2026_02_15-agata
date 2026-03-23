"""
Parser Service Module - Unified interface for different document types

Supports:
- MBOX files (email)
- Text files (.txt)
- Markdown files (.md)
- (Future: PDF, DOCX, Teams conversations)
"""

from .base_parser import BaseDocumentParser
from .text_parser import TextFileParserService
from .markdown_parser import MarkdownParserService

__all__ = [
    'BaseDocumentParser',
    'TextFileParserService',
    'MarkdownParserService',
]

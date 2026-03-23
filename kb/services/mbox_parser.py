"""
MBOX Parser Service - Extract emails from Google Takeout MBOX files
"""
import mailbox
import email
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from email.utils import parsedate_to_datetime, parseaddr
from html import unescape
import re


class MboxParserService:
    """Parse MBOX files and extract structured email data"""

    def __init__(self, output_dir: str = '/var/www/astrogen/kb_data/gmail_parsed'):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.output_dir / 'index.json'
        self.index = self._load_index()

    def _load_index(self) -> Dict:
        """Load existing index or create new one"""
        if self.index_file.exists():
            with open(self.index_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {'emails': {}, 'metadata': {'total_emails': 0, 'last_updated': None}}

    def _save_index(self):
        """Save index to disk"""
        self.index['metadata']['last_updated'] = datetime.now().isoformat()
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump(self.index, f, indent=2, ensure_ascii=False)

    def _extract_text_from_email(self, msg: email.message.Message) -> str:
        """Extract plain text content from email message"""
        text_parts = []

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == 'text/plain':
                    try:
                        payload = part.get_payload(decode=True)
                        charset = part.get_content_charset() or 'utf-8'
                        text_parts.append(payload.decode(charset, errors='ignore'))
                    except Exception as e:
                        print(f"Warning: Could not decode text part: {e}")
                elif content_type == 'text/html' and not text_parts:
                    # Fallback to HTML if no plain text found
                    try:
                        payload = part.get_payload(decode=True)
                        charset = part.get_content_charset() or 'utf-8'
                        html_text = payload.decode(charset, errors='ignore')
                        # Basic HTML stripping
                        text = re.sub(r'<[^>]+>', '', html_text)
                        text = unescape(text)
                        text_parts.append(text)
                    except Exception as e:
                        print(f"Warning: Could not decode HTML part: {e}")
        else:
            # Single part message
            try:
                payload = msg.get_payload(decode=True)
                charset = msg.get_content_charset() or 'utf-8'
                text_parts.append(payload.decode(charset, errors='ignore'))
            except Exception as e:
                print(f"Warning: Could not decode message: {e}")

        return '\n\n'.join(text_parts).strip()

    def _generate_message_id(self, msg: email.message.Message, index: int) -> str:
        """Generate unique ID for email message"""
        msg_id = msg.get('Message-ID', '')
        if msg_id:
            # Use Message-ID header if available
            return hashlib.md5(msg_id.encode()).hexdigest()
        else:
            # Fallback: hash of subject + from + date
            subject = msg.get('Subject', '')
            from_addr = msg.get('From', '')
            date = msg.get('Date', '')
            unique_str = f"{subject}{from_addr}{date}{index}"
            return hashlib.md5(unique_str.encode()).hexdigest()

    def parse_mbox_file(self, mbox_path: str, label: Optional[str] = None) -> Dict:
        """
        Parse a single MBOX file and extract all emails

        Args:
            mbox_path: Path to .mbox file
            label: Optional label/category for emails (e.g., 'INBOX', 'Sent')

        Returns:
            Dict with parsing statistics
        """
        mbox_path = Path(mbox_path)
        if not mbox_path.exists():
            raise FileNotFoundError(f"MBOX file not found: {mbox_path}")

        print(f"Parsing MBOX file: {mbox_path}")
        print(f"Label: {label or 'Unknown'}")

        mbox = mailbox.mbox(str(mbox_path))

        stats = {
            'total_messages': 0,
            'parsed_successfully': 0,
            'skipped_duplicates': 0,
            'errors': 0
        }

        for idx, msg in enumerate(mbox):
            try:
                # Generate unique message ID
                msg_id = self._generate_message_id(msg, idx)

                # Skip if already indexed
                if msg_id in self.index['emails']:
                    stats['skipped_duplicates'] += 1
                    continue

                # Extract email metadata
                subject = msg.get('Subject', '(No Subject)')
                from_header = msg.get('From', '')
                from_name, from_email = parseaddr(from_header)
                to_header = msg.get('To', '')
                cc_header = msg.get('Cc', '')
                date_header = msg.get('Date')

                # Parse date
                try:
                    date_obj = parsedate_to_datetime(date_header) if date_header else None
                    date_iso = date_obj.isoformat() if date_obj else None
                except Exception:
                    date_iso = None

                # Extract body text
                body_text = self._extract_text_from_email(msg)

                # Build structured email object
                email_data = {
                    'id': msg_id,
                    'message_id_header': msg.get('Message-ID', ''),
                    'subject': subject,
                    'from': {
                        'name': from_name,
                        'email': from_email
                    },
                    'to': to_header,
                    'cc': cc_header,
                    'date': date_iso,
                    'label': label,
                    'body_text': body_text[:5000],  # Limit to 5000 chars for storage
                    'body_length': len(body_text),
                    'has_attachments': any(
                        part.get_content_disposition() == 'attachment'
                        for part in msg.walk()
                    ) if msg.is_multipart() else False,
                    'mbox_source': mbox_path.name,
                    'indexed_at': datetime.now().isoformat()
                }

                # Save individual email to JSON file
                email_file = self.output_dir / f"{msg_id}.json"
                with open(email_file, 'w', encoding='utf-8') as f:
                    json.dump(email_data, f, indent=2, ensure_ascii=False)

                # Update index
                self.index['emails'][msg_id] = {
                    'subject': subject,
                    'from_email': from_email,
                    'date': date_iso,
                    'label': label,
                    'file_path': str(email_file),
                    'body_length': len(body_text)
                }

                stats['parsed_successfully'] += 1
                stats['total_messages'] += 1

                if stats['parsed_successfully'] % 100 == 0:
                    print(f"  Parsed {stats['parsed_successfully']} emails...")

            except Exception as e:
                print(f"Error parsing message {idx}: {e}")
                stats['errors'] += 1
                stats['total_messages'] += 1

        # Update metadata
        self.index['metadata']['total_emails'] = len(self.index['emails'])
        self._save_index()

        print(f"\nParsing complete:")
        print(f"  Total messages: {stats['total_messages']}")
        print(f"  Successfully parsed: {stats['parsed_successfully']}")
        print(f"  Skipped (duplicates): {stats['skipped_duplicates']}")
        print(f"  Errors: {stats['errors']}")

        return stats

    def parse_multiple_mbox_files(self, mbox_dir: str, label_map: Optional[Dict[str, str]] = None) -> Dict:
        """
        Parse all MBOX files in a directory

        Args:
            mbox_dir: Directory containing .mbox files
            label_map: Optional mapping of filename → label (e.g., {'Inbox.mbox': 'INBOX'})

        Returns:
            Combined statistics
        """
        mbox_dir = Path(mbox_dir)
        mbox_files = list(mbox_dir.glob('*.mbox'))

        if not mbox_files:
            raise ValueError(f"No .mbox files found in {mbox_dir}")

        print(f"Found {len(mbox_files)} MBOX files to parse")

        total_stats = {
            'files_processed': 0,
            'total_messages': 0,
            'parsed_successfully': 0,
            'skipped_duplicates': 0,
            'errors': 0
        }

        for mbox_file in mbox_files:
            label = label_map.get(mbox_file.name) if label_map else mbox_file.stem

            file_stats = self.parse_mbox_file(str(mbox_file), label=label)

            total_stats['files_processed'] += 1
            total_stats['total_messages'] += file_stats['total_messages']
            total_stats['parsed_successfully'] += file_stats['parsed_successfully']
            total_stats['skipped_duplicates'] += file_stats['skipped_duplicates']
            total_stats['errors'] += file_stats['errors']

        return total_stats

    def get_indexed_emails_summary(self) -> Dict:
        """Get summary of indexed emails"""
        return {
            'total_emails': self.index['metadata']['total_emails'],
            'last_updated': self.index['metadata']['last_updated'],
            'labels': self._get_label_distribution(),
            'date_range': self._get_date_range()
        }

    def _get_label_distribution(self) -> Dict[str, int]:
        """Count emails by label"""
        distribution = {}
        for email_info in self.index['emails'].values():
            label = email_info.get('label', 'Unknown')
            distribution[label] = distribution.get(label, 0) + 1
        return distribution

    def _get_date_range(self) -> Dict[str, Optional[str]]:
        """Get earliest and latest email dates"""
        dates = [
            email_info.get('date')
            for email_info in self.index['emails'].values()
            if email_info.get('date')
        ]

        if dates:
            return {
                'earliest': min(dates),
                'latest': max(dates)
            }
        return {'earliest': None, 'latest': None}


if __name__ == '__main__':
    # Test parser
    parser = MboxParserService()
    summary = parser.get_indexed_emails_summary()
    print(json.dumps(summary, indent=2))

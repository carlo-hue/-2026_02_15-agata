# agata/admin/services/google_drive_service.py
"""
Google Drive Integration Service

Gestisce download/upload file su Google Drive via OAuth 2.0 Device Flow.
"""
import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Callable

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import googleapiclient.discovery
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)

# Google Drive API scope
SCOPES = ['https://www.googleapis.com/auth/drive']


class GoogleDriveService:
    """Gestione operazioni Google Drive via OAuth 2.0."""

    def __init__(self):
        """Inizializza servizio Google Drive con OAuth credentials."""
        self.client_secret_file = os.getenv(
            'GOOGLE_CLIENT_SECRET_FILE',
            '/dati/codice/pythonvast/client_secret.json'
        )

        if not Path(self.client_secret_file).exists():
            raise FileNotFoundError(
                f"Google client secret JSON not found: {self.client_secret_file}\n"
                "Download from: https://console.cloud.google.com/apis/credentials\n"
                "Create 'Desktop application' OAuth 2.0 credentials and save as client_secret.json"
            )

        self.token_dir = Path.home() / '.agata'
        self.token_file = self.token_dir / 'google_drive_token.json'

        creds = self._get_credentials()
        self.service = googleapiclient.discovery.build(
            'drive', 'v3', credentials=creds
        )

        logger.info("GoogleDriveService initialized with OAuth 2.0")

    def _get_credentials(self) -> Credentials:
        """
        Get or refresh Google OAuth credentials.

        First run: Opens browser for user authentication
        Subsequent runs: Uses cached token (auto-refresh if expired)
        """
        creds = None

        # Try to load cached token
        if self.token_file.exists():
            try:
                creds = Credentials.from_authorized_user_file(
                    self.token_file, SCOPES
                )
                logger.debug(f"Loaded cached credentials from {self.token_file}")
            except Exception as e:
                logger.warning(f"Failed to load cached credentials: {e}")

        # Refresh if needed
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                self._save_credentials(creds)
                logger.info("Refreshed expired OAuth credentials")
            except Exception as e:
                logger.error(f"Failed to refresh credentials: {e}")
                creds = None

        # If no valid credentials, create new ones
        if not creds or not creds.valid:
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.client_secret_file, SCOPES
                )
                creds = flow.run_local_server(port=0)
                self._save_credentials(creds)
                logger.info("Created new OAuth credentials (user authenticated)")
            except Exception as e:
                logger.error(f"OAuth authentication failed: {e}")
                raise

        return creds

    def _save_credentials(self, creds: Credentials):
        """Save credentials to local file for reuse."""
        try:
            self.token_dir.mkdir(parents=True, exist_ok=True)
            with open(self.token_file, 'w') as f:
                f.write(creds.to_json())
            self.token_file.chmod(0o600)  # Only user can read
            logger.debug(f"Saved credentials to {self.token_file}")
        except Exception as e:
            logger.error(f"Failed to save credentials: {e}")

    def list_folder_contents(
        self,
        folder_id: str,
        file_extension: str = None,
        file_extensions: List[str] = None
    ) -> List[Dict]:
        """
        Elenca file in una folder Google Drive.

        Supporta sia folder personali che Shared Drives.

        Args:
            folder_id: Google Drive folder ID
            file_extension: Filtro opzionale singola estensione (es. '.fits')
            file_extensions: Filtro opzionale lista estensioni (es. ['.fits', '.fit'])

        Returns:
            Lista di dict metadati file
        """
        try:
            query = f"'{folder_id}' in parents and trashed=false"

            # Use corpora='user' + supportsTeamDrives + includeTeamDriveItems
            results = self.service.files().list(
                q=query,
                corpora='user',
                supportsTeamDrives=True,
                includeTeamDriveItems=True,
                fields='files(id, name, mimeType, size)',
                pageSize=1000
            ).execute()

            files = results.get('files', [])

            # Filter by extension(s)
            if file_extensions:
                # Multiple extensions
                exts_lower = [ext.lower() for ext in file_extensions]
                files = [
                    f for f in files
                    if any(f['name'].lower().endswith(ext) for ext in exts_lower)
                ]
            elif file_extension:
                # Single extension
                files = [
                    f for f in files
                    if f['name'].lower().endswith(file_extension.lower())
                ]

            logger.info(f"Found {len(files)} files in folder {folder_id}")
            return files

        except Exception as e:
            logger.error(f"Failed to list folder {folder_id}: {e}", exc_info=True)
            raise

    def calculate_folder_size(self, folder_id: str) -> int:
        """
        Calcola dimensione totale folder (in bytes).

        Args:
            folder_id: Google Drive folder ID

        Returns:
            Dimensione totale in bytes
        """
        try:
            files = self.list_folder_contents(folder_id)
            total_size = sum(int(f.get('size', 0)) for f in files)

            size_gb = total_size / (1024 ** 3)
            logger.info(f"Folder {folder_id} total size: {size_gb:.2f} GB")
            return total_size

        except Exception as e:
            logger.error(f"Failed to calculate folder size: {e}", exc_info=True)
            raise

    def download_folder(
        self,
        folder_id: str,
        destination_dir: str,
        file_extension: str = None,
        file_extensions: List[str] = None,
        progress_callback: Callable = None
    ) -> List[str]:
        """
        Download tutti file da Google Drive folder.

        Args:
            folder_id: Google Drive folder ID
            destination_dir: Directory locale per salvataggio
            file_extension: Filtro opzionale singola estensione
            file_extensions: Filtro opzionale lista estensioni
            progress_callback: Callback opzionale(current, total)

        Returns:
            Lista path file scaricati
        """
        try:
            files = self.list_folder_contents(folder_id, file_extension, file_extensions)
            downloaded = []

            Path(destination_dir).mkdir(parents=True, exist_ok=True)

            logger.info(f"Starting download of {len(files)} files from {folder_id}")

            for idx, file in enumerate(files):
                local_path = os.path.join(destination_dir, file['name'])

                try:
                    # Download file
                    request = self.service.files().get_media(fileId=file['id'])
                    with open(local_path, 'wb') as fh:
                        fh.write(request.execute())

                    downloaded.append(local_path)

                    logger.debug(f"Downloaded {file['name']} ({idx+1}/{len(files)})")

                    if progress_callback:
                        try:
                            progress_callback(idx + 1, len(files))
                        except Exception as e:
                            logger.warning(f"Progress callback error: {e}")

                except Exception as e:
                    logger.error(f"Failed to download {file['name']}: {e}")
                    # Continue with next file

            logger.info(f"Download complete: {len(downloaded)}/{len(files)} files")
            return downloaded

        except Exception as e:
            logger.error(f"Folder download failed: {e}", exc_info=True)
            raise

    def upload_file(
        self,
        local_path: str,
        folder_id: str,
        title: str = None
    ) -> str:
        """
        Upload file a Google Drive.

        Args:
            local_path: Path file locale
            folder_id: Target Google Drive folder ID
            title: Nome file custom (opzionale)

        Returns:
            Google Drive file ID
        """
        try:
            if not title:
                title = os.path.basename(local_path)

            if not os.path.exists(local_path):
                raise FileNotFoundError(f"Local file not found: {local_path}")

            # File metadata
            file_metadata = {
                'name': title,
                'parents': [folder_id]
            }

            # Upload with resumable media
            media = MediaFileUpload(
                local_path,
                resumable=True,
                chunksize=10 * 1024 * 1024  # 10MB chunks
            )

            request = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            )

            response = None
            while response is None:
                try:
                    status, response = request.next_chunk()
                    if status:
                        logger.debug(f"Upload progress: {int(status.progress() * 100)}%")
                except Exception as e:
                    logger.error(f"Upload error: {e}")
                    raise

            file_id = response.get('id')
            logger.info(f"Uploaded {title} to folder {folder_id}, file ID: {file_id}")
            return file_id

        except Exception as e:
            logger.error(f"File upload failed: {e}", exc_info=True)
            raise

    def create_folder(self, folder_name: str, parent_id: str = None) -> str:
        """
        Crea nuova folder su Google Drive.

        Args:
            folder_name: Nome della folder
            parent_id: Parent folder ID (opzionale)

        Returns:
            ID della folder creata
        """
        try:
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }

            if parent_id:
                file_metadata['parents'] = [parent_id]

            folder = self.service.files().create(
                body=file_metadata,
                fields='id'
            ).execute()

            folder_id = folder.get('id')
            logger.info(f"Created folder {folder_name}, ID: {folder_id}")
            return folder_id

        except Exception as e:
            logger.error(f"Folder creation failed: {e}", exc_info=True)
            raise

    def list_folders(self, limit: int = 10) -> List[Dict]:
        """
        Lista ultime N folder di Google Drive ordinate per data modifica.
        Include sia cartelle personali che cartelle condivise (Shared Drives).

        Args:
            limit: Numero di folder da listare (default 10)

        Returns:
            Lista di dict con folder info:
            [
                {
                    'id': folder_id,
                    'name': folder_name,
                    'file_count': numero_file_immagine,
                    'modified_time': data_modifica,
                    'url': google_drive_url
                },
                ...
            ]
        """
        try:
            # Query: Personal + Shared folders (accessible to user)
            # Using corpora='user' includes personal drive AND folders shared with me
            query = "mimeType='application/vnd.google-apps.folder' and trashed=false"
            results = self.service.files().list(
                q=query,
                corpora='user',  # Personal drive + shared with me
                fields='files(id, name, modifiedTime)',
                pageSize=limit * 2,
                orderBy='modifiedTime desc'
            ).execute()

            all_folders = results.get('files', [])
            logger.info(f"Found {len(all_folders)} folders (personal + shared with me)")

            # Sort by modified time and limit
            all_folders = sorted(
                all_folders,
                key=lambda x: x.get('modifiedTime', ''),
                reverse=True
            )[:limit]

            # For each folder, count image files
            folder_list = []
            for folder in all_folders:
                try:
                    # Count image files in this folder
                    # Support both .fit/.fits and image MIME types
                    file_query = f"'{folder['id']}' in parents and trashed=false and (mimeType contains 'image' or name contains '.fit')"

                    # Use corpora='user' for personal + shared folders
                    file_results = self.service.files().list(
                        q=file_query,
                        corpora='user',  # Same as folder query
                        fields='files(id)',
                        pageSize=1000
                    ).execute()

                    file_count = len(file_results.get('files', []))
                    logger.debug(f"Folder {folder['name']} ({folder['id']}): {file_count} files")

                    folder_list.append({
                        'id': folder['id'],
                        'name': folder['name'],
                        'file_count': file_count,
                        'modified_time': folder.get('modifiedTime'),
                        'url': f"https://drive.google.com/drive/folders/{folder['id']}"
                    })

                except Exception as e:
                    logger.warning(f"Error counting files in folder {folder['id']}: {e}")
                    # Still add folder even if count fails
                    folder_list.append({
                        'id': folder['id'],
                        'name': folder['name'],
                        'file_count': 0,
                        'modified_time': folder.get('modifiedTime'),
                        'url': f"https://drive.google.com/drive/folders/{folder['id']}"
                    })

            logger.info(f"Found {len(folder_list)} folders total (personal + shared drives)")
            return folder_list

        except Exception as e:
            logger.error(f"Failed to list folders: {e}", exc_info=True)
            raise

    def list_subfolders(self, parent_folder_id: str) -> List[Dict]:
        """
        Lista sottocartelle dentro una cartella parent di Google Drive.
        Conta anche i file FITS (.fit, .fits) dentro ogni sottocartella.

        Supporta sia folder personali che Shared Drives.

        Args:
            parent_folder_id: ID della cartella parent (es. 1vhsDXOHMH1ruOICY6Sp3ljTTFxLiptVs)

        Returns:
            Lista di dict con subfolder info:
            [
                {
                    'id': subfolder_id,
                    'name': subfolder_name,
                    'file_count': numero_file_fits,
                    'url': google_drive_url
                },
                ...
            ]
        """
        try:
            # Query: lista solo sottocartelle dentro parent_folder_id
            query = f"'{parent_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"

            logger.debug(f"Querying subfolders with parent_folder_id: {parent_folder_id}")

            # Use corpora='user' + supportsTeamDrives + includeTeamDriveItems for Shared Drives
            results = self.service.files().list(
                q=query,
                corpora='user',
                supportsTeamDrives=True,
                includeTeamDriveItems=True,
                fields='files(id, name, modifiedTime)',
                pageSize=1000,
                orderBy='modifiedTime desc'
            ).execute()

            subfolders = results.get('files', [])
            logger.info(f"Found {len(subfolders)} subfolders in parent {parent_folder_id}")

            # For each subfolder, count FITS files
            subfolder_list = []
            for subfolder in subfolders:
                try:
                    # Count FITS files in this subfolder
                    file_query = f"'{subfolder['id']}' in parents and trashed=false and (name contains '.fit' or name contains '.fits')"

                    file_results = self.service.files().list(
                        q=file_query,
                        corpora='user',
                        supportsTeamDrives=True,
                        includeTeamDriveItems=True,
                        fields='files(id)',
                        pageSize=1000
                    ).execute()

                    file_count = len(file_results.get('files', []))
                    logger.debug(f"Subfolder {subfolder['name']} ({subfolder['id']}): {file_count} FITS files")

                    subfolder_list.append({
                        'id': subfolder['id'],
                        'name': subfolder['name'],
                        'file_count': file_count,
                        'url': f"https://drive.google.com/drive/folders/{subfolder['id']}"
                    })

                except Exception as e:
                    logger.warning(f"Error counting FITS files in subfolder {subfolder['id']}: {e}")
                    # Still add subfolder even if count fails
                    subfolder_list.append({
                        'id': subfolder['id'],
                        'name': subfolder['name'],
                        'file_count': 0,
                        'url': f"https://drive.google.com/drive/folders/{subfolder['id']}"
                    })

            logger.info(f"Found {len(subfolder_list)} subfolders with FITS files info")
            return subfolder_list

        except Exception as e:
            logger.error(f"Failed to list subfolders: {e}", exc_info=True)
            raise

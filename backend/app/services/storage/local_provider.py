import uuid
import aiofiles
import aiofiles.os
import logging
from pathlib import Path

from app.services.storage.base import StorageProvider

logger = logging.getLogger(__name__)


class LocalStorageProvider(StorageProvider):
    """Local filesystem storage provider."""
    
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Initialized local storage at: {self.base_dir}")
    
    async def save_file(self, file_bytes: bytes, filename: str) -> str:
        """Save file to local storage with UUID prefix."""
        # Generate unique filename
        ext = Path(filename).suffix
        unique_name = f"{uuid.uuid4()}{ext}"
        file_path = self.base_dir / unique_name
        
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(file_bytes)
        
        logger.info(f"Saved file: {file_path}")
        return str(file_path)
    
    async def open_file(self, file_uri: str) -> bytes:
        """Open file from local storage."""
        file_path = Path(file_uri)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_uri}")
        
        async with aiofiles.open(file_path, 'rb') as f:
            return await f.read()
    
    async def delete_file(self, file_uri: str) -> None:
        """Delete file from local storage."""
        file_path = Path(file_uri)
        
        if file_path.exists():
            await aiofiles.os.remove(file_path)
            logger.info(f"Deleted file: {file_path}")
    
    async def file_exists(self, file_uri: str) -> bool:
        """Check if file exists in local storage."""
        return Path(file_uri).exists()

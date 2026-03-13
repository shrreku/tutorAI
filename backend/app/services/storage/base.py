from abc import ABC, abstractmethod


class StorageProvider(ABC):
    """Base class for storage providers."""

    @abstractmethod
    async def save_file(self, file_bytes: bytes, filename: str) -> str:
        """
        Save a file and return its URI or path.

        Args:
            file_bytes: File content as bytes
            filename: Original filename

        Returns:
            URI or path to the stored file
        """
        pass

    @abstractmethod
    async def open_file(self, file_uri: str) -> bytes:
        """
        Open a file and return its content.

        Args:
            file_uri: URI or path to the file

        Returns:
            File content as bytes
        """
        pass

    @abstractmethod
    async def delete_file(self, file_uri: str) -> None:
        """
        Delete a file.

        Args:
            file_uri: URI or path to the file
        """
        pass

    @abstractmethod
    async def file_exists(self, file_uri: str) -> bool:
        """
        Check if a file exists.

        Args:
            file_uri: URI or path to the file

        Returns:
            True if the file exists
        """
        pass

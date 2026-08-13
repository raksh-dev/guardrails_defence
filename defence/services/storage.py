from typing import Protocol


class StorageService(Protocol):
    """
    Interface every storage backend must satisfy.
    Swap Supabase for S3, GCS, or local disk by implementing this protocol —
    nothing else in the codebase changes.
    """

    def upload(
        self,
        destination_path: str,
        file_bytes: bytes,
        content_type: str,
    ) -> str:
        """
        Upload file bytes to the given path.
        Returns the storage path that was written (used to construct URLs).
        """
        ...

    def download(self, storage_path: str) -> bytes:
        """
        Download raw file bytes from storage.
        """
        ...

    def get_presigned_url(self, storage_path: str) -> str:
        """
        Return a time-limited URL the client can use to download the file.
        """
        ...

    def delete(self, storage_path: str) -> None:
        """
        Permanently remove a file from storage.
        """
        ...
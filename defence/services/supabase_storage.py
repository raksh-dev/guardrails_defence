from supabase import create_client, Client

from core.config import settings
from core.exceptions import StorageUploadException, StorageDeleteException


class SupabaseStorageService:
    """Supabase implementation of the StorageService protocol."""

    @property
    def client(self) -> Client:
        """Expose the underlying Supabase client for reuse by other Supabase-backed services."""
        return self._client


    def __init__(self):
        self._client: Client = create_client(
            settings.STORAGE_URL,
            settings.STORAGE_ACCOUNT_SECRET,
        )
        self._bucket = settings.STORAGE_BUCKET_NAME

    def upload(
        self,
        destination_path: str,
        file_bytes: bytes,
        content_type: str,
    ) -> str:
        try:
            self._client.storage.from_(self._bucket).upload(
                path= destination_path,
                file=file_bytes,
                file_options={
                    "content-type": content_type,
                    "upsert": "false",
                },
            )
            return destination_path
        except Exception as e:
            raise StorageUploadException(f"Failed to upload file to storage: {e}")


    def download(self, storage_path: str) -> bytes:
        """Download raw file bytes from Supabase storage."""
        try:
            return self._client.storage.from_(self._bucket).download(storage_path)
        except Exception as e:
            raise StorageDeleteException(f"Failed to download file from storage: {e}")

    def get_presigned_url(self, storage_path: str) -> str:
        response = self._client.storage.from_(self._bucket).create_signed_url(
            path=storage_path,
            expires_in=settings.STORAGE_PRESIGNED_URL_EXPIRY,
        )
        return response["signedURL"]

    def delete(self, storage_path: str) -> None:
        try:
            self._client.storage.from_(self._bucket).remove([storage_path])
        except Exception as e:
            raise StorageDeleteException(f"Failed to delete file from storage: {e}")


# Singleton
supabase_storage = SupabaseStorageService()


def get_storage_service() -> SupabaseStorageService:
    return supabase_storage
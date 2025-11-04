import hashlib
from typing import Optional
import boto3
import requests
from urllib.parse import urlparse
import os
from botocore.exceptions import ClientError

from jedwal.config import settings


class ImageHandler:

    def __init__(
        self, bucket_location: Optional[str] = None, bucket_url: Optional[str] = None
    ):
        self.bucket_location = (
            bucket_location or settings.image_storage_bucket
        )
        self.bucket_url = bucket_url or settings.image_storage_bucket_url
        self.s3_client = boto3.client("s3")

    def upload(self, src: str) -> str:
        """Upload an image from URL to S3 bucket. 

        Deduplicates by SHA256 hash of the image bytes.
        """
        self._check_src_is_url(src)

        image_data = self._download_image(src)
        file_extension = self._get_file_extension(src)
        image_hash = hashlib.sha256(image_data).hexdigest()
        object_key = f"images/{image_hash}{file_extension}"

        # Only upload if an image with these same bytes
        # doesn't already exist. Otherwise, it means
        # we've already processed this image earlier.
        if not self._object_exists(object_key):
            self._upload_to_s3(image_data, object_key)

        return f"{self.bucket_url}/{object_key}"

    def delete(self, url: str):
        """Delete an image from the S3 bucket given its URL"""
        if not url.startswith(self.bucket_url):
            raise ValueError(f"URL does not belong to this bucket: {url}")

        # Extract the object key (everything after the bucket_url + '/')
        object_key = url.replace(f"{self.bucket_url}/", "", 1)

        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_location,
                Key=object_key,
            )
        except ClientError as e:
            raise ClientError(f"Failed to delete from S3: {str(e)}")

    def _check_src_is_url(self, url: str):
        if not url.startswith("https://"):
            raise ValueError(f"Cannot upload source that is not url: {url}")

    def _download_image(self, url: str) -> bytes:
        """Download image from URL and return bytes"""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }

            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            # Verify it's an image by checking content type
            content_type = response.headers.get("content-type", "")
            if not content_type.startswith("image/"):
                raise ValueError(
                    f"URL does not point to an image. Content-Type: {content_type}"
                )

            return response.content

        except requests.RequestException as e:
            raise requests.RequestException(
                f"Failed to download image from {url}: {str(e)}"
            )

    def _get_file_extension(self, url: str) -> str:
        """Extract file extension from URL or content type"""
        parsed_url = urlparse(url)
        path = parsed_url.path

        if path:
            _, ext = os.path.splitext(path)
            if ext.lower() in [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"]:
                return ext.lower()
        return ".jpg"

    def _upload_to_s3(self, image_data: bytes, object_key: str):
        """Upload image data to S3 bucket"""
        try:
            self.s3_client.put_object(
                Bucket=self.bucket_location,
                Key=object_key,
                Body=image_data,
                ContentType=self._get_content_type(object_key),
            )
        except ClientError as e:
            raise ClientError(f"Failed to upload to S3: {str(e)}")

    def _get_content_type(self, filename: str) -> str:
        """Get appropriate content type based on file extension"""
        ext = os.path.splitext(filename)[1].lower()
        content_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
            ".webp": "image/webp",
        }
        return content_types.get(ext, "image/jpeg")

    def _object_exists(self, key: str) -> bool:
        """Return True if object exists in S3, else False."""
        try:
            self.s3_client.head_object(
                Bucket=self.bucket_location,
                Key=key,
            )
            return True
        except self.s3_client.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise

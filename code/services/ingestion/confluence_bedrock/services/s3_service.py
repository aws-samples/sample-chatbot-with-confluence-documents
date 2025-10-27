"""
S3 service for handling attachment storage and retrieval
"""
import boto3
import logging
from typing import Optional, Dict, Any
from urllib.parse import urlparse
import os
from botocore.exceptions import ClientError, NoCredentialsError

from ..models.config_models import Config

logger = logging.getLogger(__name__)


class S3Service:
    """Service for interacting with S3 for attachment storage"""
    
    def __init__(self, config: Config):
        self.config = config
        self.region = config.aws_region
        self.attachments_path = config.s3_attachments_path
        
        # Parse S3 path
        parsed = urlparse(self.attachments_path)
        if parsed.scheme != 's3':
            raise ValueError(f"Invalid S3 path format: {self.attachments_path}")
        
        self.bucket_name = parsed.netloc
        self.base_prefix = parsed.path.lstrip('/')
        
        # Initialize S3 client
        try:
            self.s3_client = boto3.client('s3', region_name=self.region)
            logger.info(f"S3 client initialized for region: {self.region}")
        except NoCredentialsError:
            logger.warning("AWS credentials not found")
            raise
        except Exception as e:
            logger.warning(f"Failed to initialize S3 client: {e}")
            raise
    
    def upload_attachment(self, file_content: bytes, page_id: str, attachment_id: str, 
                         filename: str, content_type: str = None) -> str:
        """
        Upload attachment to S3
        
        Args:
            file_content: Binary content of the file
            page_id: Confluence page ID
            attachment_id: Confluence attachment ID
            filename: Original filename
            content_type: MIME type of the file
            
        Returns:
            S3 URI of the uploaded file
        """
        try:
            # Create S3 key: base_prefix/page_id/attachment_id_filename
            s3_key = f"{self.base_prefix}{page_id}/{attachment_id}_{filename}"
            
            # Prepare upload parameters
            upload_params = {
                'Bucket': self.bucket_name,
                'Key': s3_key,
                'Body': file_content,
                'StorageClass': 'INTELLIGENT_TIERING'
            }
            
            if content_type:
                upload_params['ContentType'] = content_type
            
            # Upload to S3
            self.s3_client.put_object(**upload_params)
            
            s3_uri = f"s3://{self.bucket_name}/{s3_key}"
            logger.info(f"Successfully uploaded attachment to S3: {s3_uri}")
            
            return s3_uri
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.warning(f"S3 upload failed with error {error_code}: {e}")
            raise
        except Exception as e:
            logger.warning(f"Failed to upload attachment to S3: {e}")
            raise
    
    def download_attachment(self, s3_uri: str, local_path: str) -> bool:
        """
        Download attachment from S3 to local file
        
        Args:
            s3_uri: S3 URI of the file
            local_path: Local path where to save the file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Parse S3 URI
            parsed = urlparse(s3_uri)
            if parsed.scheme != 's3':
                logger.error(f"Invalid S3 URI format: {s3_uri}")
                return False
            
            bucket = parsed.netloc
            key = parsed.path.lstrip('/')
            
            # Ensure local directory exists
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            # Download from S3
            self.s3_client.download_file(bucket, key, local_path)
            
            logger.debug(f"Successfully downloaded {s3_uri} to {local_path}")
            return True
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                logger.error(f"File not found in S3: {s3_uri}")
            else:
                logger.error(f"S3 download failed with error {error_code}: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to download attachment from S3: {e}")
            return False
    
    def check_attachment_exists(self, s3_uri: str) -> bool:
        """
        Check if attachment exists in S3
        
        Args:
            s3_uri: S3 URI of the file
            
        Returns:
            True if file exists, False otherwise
        """
        try:
            # Parse S3 URI
            parsed = urlparse(s3_uri)
            if parsed.scheme != 's3':
                return False
            
            bucket = parsed.netloc
            key = parsed.path.lstrip('/')
            
            # Check if object exists
            self.s3_client.head_object(Bucket=bucket, Key=key)
            return True
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                return False
            else:
                logger.error(f"Error checking S3 object existence: {e}")
                return False
        except Exception as e:
            logger.error(f"Failed to check S3 object existence: {e}")
            return False
    
    def get_attachment_info(self, s3_uri: str) -> Optional[Dict[str, Any]]:
        """
        Get attachment metadata from S3
        
        Args:
            s3_uri: S3 URI of the file
            
        Returns:
            Dictionary with file metadata or None if not found
        """
        try:
            # Parse S3 URI
            parsed = urlparse(s3_uri)
            if parsed.scheme != 's3':
                return None
            
            bucket = parsed.netloc
            key = parsed.path.lstrip('/')
            
            # Get object metadata
            response = self.s3_client.head_object(Bucket=bucket, Key=key)
            
            return {
                'size': response.get('ContentLength', 0),
                'content_type': response.get('ContentType', ''),
                'last_modified': response.get('LastModified'),
                'etag': response.get('ETag', '').strip('"')
            }
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code != '404':  # Don't log 404 as error
                logger.error(f"Error getting S3 object metadata: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to get S3 object metadata: {e}")
            return None
    
    def delete_attachment(self, s3_uri: str) -> bool:
        """
        Delete attachment from S3
        
        Args:
            s3_uri: S3 URI of the file to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Parse S3 URI
            parsed = urlparse(s3_uri)
            if parsed.scheme != 's3':
                logger.error(f"Invalid S3 URI format: {s3_uri}")
                return False
            
            bucket = parsed.netloc
            key = parsed.path.lstrip('/')
            
            # Delete from S3
            self.s3_client.delete_object(Bucket=bucket, Key=key)
            
            logger.info(f"Successfully deleted attachment from S3: {s3_uri}")
            return True
            
        except ClientError as e:
            logger.error(f"S3 delete failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to delete attachment from S3: {e}")
            return False
    
    def list_page_attachments(self, page_id: str) -> list:
        """
        List all attachments for a specific page
        
        Args:
            page_id: Confluence page ID
            
        Returns:
            List of S3 URIs for the page's attachments
        """
        try:
            prefix = f"{self.base_prefix}{page_id}/"
            
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )
            
            attachments = []
            for obj in response.get('Contents', []):
                s3_uri = f"s3://{self.bucket_name}/{obj['Key']}"
                attachments.append(s3_uri)
            
            return attachments
            
        except ClientError as e:
            logger.error(f"Failed to list page attachments: {e}")
            return []
        except Exception as e:
            logger.error(f"Failed to list page attachments: {e}")
            return []

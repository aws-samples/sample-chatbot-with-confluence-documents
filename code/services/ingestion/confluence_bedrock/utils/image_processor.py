"""
Image processor for downloading and uploading Confluence images
"""
import os
import logging
from typing import Dict, List, Any, Optional
import urllib.parse
import base64
from urllib.parse import urlparse, unquote
import urllib3

from ..models.config_models import Config
from ..services.s3_service import S3Service

logger = logging.getLogger(__name__)


class ImageProcessor:
    """Processes images from Confluence content"""
    
    def __init__(self, config: Config, s3_service: S3Service):
        self.config = config
        self.s3_service = s3_service
        self.confluence_base_url = config.get_confluence_base_url()
        
        # Create basic auth header for Confluence
        credentials = f"{config.confluence_email}:{config.confluence_api_token}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        self.headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'User-Agent': 'Confluence-Bedrock-Integration/1.0'
        }
        
        # Create urllib3 PoolManager for HTTP requests
        self.http = urllib3.PoolManager()
    
    def process_page_images(self, page_id: str, storage_content: str, attachments: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process all images in a page's storage content"""
        result = {
            'processed_images': 0,
            'successful_uploads': 0,
            'failed_uploads': 0,
            'errors': [],
            'modified_content': storage_content
        }
        
        if not attachments:
            logger.debug(f"No attachments found for page {page_id}")
            return result
        
        # Create a lookup dictionary for attachments by filename
        attachment_lookup = {}
        for attachment in attachments:
            filename = attachment.get('title', '')
            if filename:
                attachment_lookup[filename] = attachment
        
        logger.info(f"Processing {len(attachments)} attachments for page {page_id}")
        
        # Process each attachment
        for attachment in attachments:
            try:
                filename = attachment.get('title', '')
                if not filename:
                    continue
                
                # Check if it's an image
                media_type = attachment.get('extensions', {}).get('mediaType', '')
                if not media_type.startswith('image/'):
                    logger.debug(f"Skipping non-image attachment: {filename}")
                    continue
                
                result['processed_images'] += 1
                
                # Download and upload image
                s3_uri = self._download_and_upload_image(page_id, attachment)
                
                if s3_uri:
                    result['successful_uploads'] += 1
                    # Use the actual S3 URI returned from upload
                    result['modified_content'] = self._add_s3_uri_to_content(
                        result['modified_content'], filename, s3_uri
                    )
                    logger.info(f"✅ Successfully processed image: {filename}")
                else:
                    result['failed_uploads'] += 1
                    result['errors'].append(f"Failed to upload {filename}")
                    logger.error(f"🔴 Failed to process image: {filename}")
                    
            except Exception as e:
                result['failed_uploads'] += 1
                error_msg = f"Error processing {filename}: {str(e)}"
                result['errors'].append(error_msg)
                logger.error(f"🔴 {error_msg}")
        
        logger.info(f"Image processing complete for page {page_id}: "
                   f"{result['successful_uploads']}/{result['processed_images']} successful")
        
        return result
    
    def _download_and_upload_image(self, page_id: str, attachment: Dict[str, Any]) -> Optional[str]:
        """Download image from Confluence and upload to S3
        
        Returns:
            S3 URI if successful, None if failed
        """
        try:
            filename = attachment.get('title', '')
            if not filename:
                return None
            
            # URL-encode the filename to handle spaces and Unicode characters
            encoded_filename = urllib.parse.quote(filename, safe='')
            
            # Use the simple, reliable URL format that works
            image_url = f"{self.confluence_base_url}/wiki/download/attachments/{page_id}/{encoded_filename}"
            
            logger.info(f"Downloading {filename} from: {image_url}")
            
            # Download image
            image_data = self._download_image(image_url)
            if not image_data:
                return None
            
            # Upload to S3 - let S3Service handle the path
            media_type = attachment.get('extensions', {}).get('mediaType', 'application/octet-stream')
            
            s3_uri = self.s3_service.upload_attachment(
                file_content=image_data,
                page_id=page_id,
                attachment_id=attachment.get('id', 'unknown'),
                filename=filename,
                content_type=media_type
            )
            
            if s3_uri:
                logger.debug(f"Successfully uploaded {filename} to S3: {s3_uri}")
                return s3_uri
            else:
                logger.error(f"Failed to upload {filename} to S3")
                return None
                
        except Exception as e:
            logger.error(f"Error in _download_and_upload_image for {filename}: {e}")
            return None
    
    def _validate_url_scheme(self, url: str) -> bool:
        """Validate that URL uses allowed schemes (http/https only)"""
        parsed = urllib.parse.urlparse(url)
        return parsed.scheme in ('http', 'https')
    
    def _download_image(self, image_url: str) -> Optional[bytes]:
        """Download image from URL with proper redirect handling"""
        try:
            # Validate URL scheme for security
            if not self._validate_url_scheme(image_url):
                logger.error(f"Invalid URL scheme. Only http/https allowed: {image_url}")
                return None
            
            # Use urllib3 with redirect handling
            # Follow redirects manually to preserve auth headers for Atlassian domains
            max_redirects = 5
            current_url = image_url
            
            for redirect_count in range(max_redirects):
                response = self.http.request(
                    'GET',
                    current_url,
                    headers=self.headers,
                    timeout=self.config.request_timeout,
                    redirect=False  # Handle redirects manually
                )
                
                # Success - return the data
                if response.status == 200:
                    return response.data
                
                # Handle redirects (301, 302, 303, 307, 308)
                if response.status in (301, 302, 303, 307, 308):
                    redirect_url = response.headers.get('Location')
                    if not redirect_url:
                        logger.error(f"Redirect without Location header from {current_url}")
                        return None
                    
                    # Log redirect for debugging
                    logger.info(f"Redirecting {current_url} -> {redirect_url}")
                    
                    # Update current URL for next iteration
                    current_url = redirect_url
                    continue
                
                # Other status codes are errors
                logger.error(f"HTTP {response.status} when downloading {current_url}")
                return None
            
            # Too many redirects
            logger.error(f"Too many redirects (>{max_redirects}) when downloading {image_url}")
            return None
                    
        except urllib3.exceptions.HTTPError as e:
            logger.error(f"HTTP error downloading {image_url}: {e}")
            return None
        except urllib3.exceptions.MaxRetryError as e:
            logger.error(f"Connection error downloading {image_url}: {e}")
            return None
        except urllib3.exceptions.TimeoutError as e:
            logger.error(f"Timeout error downloading {image_url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error downloading {image_url}: {e}")
            return None
    
    def _add_s3_uri_to_content(self, content: str, filename: str, s3_uri: str) -> str:
        """Add S3 URI to ri:attachment tags in content"""
        import re
        
        # Pattern to find ri:attachment tags with the specific filename
        pattern = f'(<ri:attachment[^>]*ri:filename="{re.escape(filename)}"[^>]*)(/>)'
        
        # Replace with version that includes S3 URI
        def replacement(match):
            tag_start = match.group(1)
            tag_end = match.group(2)
            
            # Add S3 URI attribute if not already present
            if 'ri:s3-uri=' not in tag_start:
                return f'{tag_start} ri:s3-uri="{s3_uri}"{tag_end}'
            else:
                # Update existing S3 URI
                updated_tag = re.sub(
                    r'ri:s3-uri="[^"]*"',
                    f'ri:s3-uri="{s3_uri}"',
                    tag_start
                )
                return f'{updated_tag}{tag_end}'
        
        modified_content = re.sub(pattern, replacement, content)
        
        # Also handle ac:image tags that contain ri:attachment
        ac_image_pattern = f'(<ac:image[^>]*>.*?<ri:attachment[^>]*ri:filename="{re.escape(filename)}"[^>]*)(/>)(.*?</ac:image>)'
        
        def ac_image_replacement(match):
            before_attachment = match.group(1)
            attachment_end = match.group(2)
            after_attachment = match.group(3)
            
            # Add S3 URI to the ri:attachment tag
            if 'ri:s3-uri=' not in before_attachment:
                updated_attachment = f'{before_attachment} ri:s3-uri="{s3_uri}"{attachment_end}'
            else:
                # Update existing S3 URI
                updated_attachment = re.sub(
                    r'ri:s3-uri="[^"]*"',
                    f'ri:s3-uri="{s3_uri}"',
                    before_attachment
                ) + attachment_end
            
            return f'{updated_attachment}{after_attachment}'
        
        modified_content = re.sub(ac_image_pattern, ac_image_replacement, modified_content, flags=re.DOTALL)
        
        return modified_content

"""
Confluence API service
"""
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import urllib.parse
import base64
import urllib3

from ..models.config_models import Config
from ..models.confluence_models import ConfluencePage, PageVersion, ConfluenceSpace

logger = logging.getLogger(__name__)


class ConfluenceService:
    """Service for interacting with Confluence API"""
    
    def __init__(self, config: Config):
        self.config = config
        self.base_url = config.get_confluence_base_url()
        
        # Create basic auth header
        credentials = f"{config.confluence_email}:{config.confluence_api_token}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        self.headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': f'Basic {encoded_credentials}'
        }
        
        # Create urllib3 PoolManager for HTTP requests
        self.http = urllib3.PoolManager()
    
    def _validate_url_scheme(self, url: str) -> bool:
        """Validate that URL uses allowed schemes (http/https only)"""
        parsed = urllib.parse.urlparse(url)
        return parsed.scheme in ('http', 'https')
    
    def _make_request(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make HTTP request to Confluence API"""
        try:
            # Validate URL scheme for security
            if not self._validate_url_scheme(url):
                raise ValueError(f"Invalid URL scheme. Only http/https allowed: {url}")
            
            # Add query parameters if provided
            if params:
                query_string = urllib.parse.urlencode(params)
                url = f"{url}?{query_string}"
            
            # Make request with timeout using urllib3
            response = self.http.request(
                'GET',
                url,
                headers=self.headers,
                timeout=self.config.request_timeout
            )
            
            # Check status code
            if response.status == 200:
                data = response.data.decode('utf-8')
                return json.loads(data)
            else:
                raise urllib3.exceptions.HTTPError(
                    f"HTTP {response.status} for URL {url}"
                )
                    
        except urllib3.exceptions.HTTPError as e:
            logger.warning(f"HTTP error for URL {url}: {e}")
            raise
        except urllib3.exceptions.MaxRetryError as e:
            logger.warning(f"Connection error for {url}: {e}")
            raise
        except urllib3.exceptions.TimeoutError as e:
            logger.warning(f"Timeout error for {url}: {e}")
            raise
        except json.JSONDecodeError as e:
            logger.warning(f"JSON decode error for {url}: {e}")
            raise
        except Exception as e:
            logger.warning(f"Unexpected error for {url}: {e}")
            raise
    
    def get_space_info(self, space_key: str) -> Optional[ConfluenceSpace]:
        """Get information about a Confluence space"""
        try:
            url = f"{self.base_url}/wiki/rest/api/space/{space_key}"
            data = self._make_request(url)
            
            return ConfluenceSpace(
                id=data['id'],
                key=data['key'],
                name=data['name'],
                type=data['type'],
                status=data['status']
            )
            
        except Exception as e:
            logger.error(f"Failed to get space info for {space_key}: {e}")
            return None
    
    def get_pages_in_space(self, space_key: str, limit: int = 100) -> List[ConfluencePage]:
        """Get all pages in a Confluence space"""
        pages = []
        start = 0
        
        while True:
            try:
                url = f"{self.base_url}/wiki/rest/api/content"
                params = {
                    'spaceKey': space_key,
                    'type': 'page',
                    'status': 'current',
                    'expand': 'version,space,body.storage',
                    'limit': limit,
                    'start': start
                }
                
                data = self._make_request(url, params)
                
                # Process results
                for page_data in data.get('results', []):
                    page = self._parse_page_data(page_data)
                    if page:
                        pages.append(page)
                
                # Check if there are more pages
                if len(data.get('results', [])) < limit:
                    break
                
                start += limit
                
            except Exception as e:
                logger.error(f"Failed to get pages for space {space_key}: {e}")
                break
        
        logger.info(f"Retrieved {len(pages)} pages from space {space_key}")
        return pages
    
    def get_page_by_id(self, page_id: str) -> Optional[ConfluencePage]:
        """Get a specific page by ID"""
        try:
            url = f"{self.base_url}/wiki/rest/api/content/{page_id}"
            params = {
                'expand': 'version,space,body.storage'
            }
            
            data = self._make_request(url, params)
            return self._parse_page_data(data)
            
        except Exception as e:
            logger.error(f"Failed to get page {page_id}: {e}")
            return None
    
    def get_page_attachments(self, page_id: str) -> List[Dict[str, Any]]:
        """Get attachments for a page"""
        try:
            url = f"{self.base_url}/wiki/rest/api/content/{page_id}/child/attachment"
            params = {
                'expand': 'version,metadata,extensions'
            }
            
            data = self._make_request(url, params)
            return data.get('results', [])
            
        except Exception as e:
            logger.error(f"Failed to get attachments for page {page_id}: {e}")
            return []
    
    def _parse_page_data(self, page_data: Dict[str, Any]) -> Optional[ConfluencePage]:
        """Parse page data from Confluence API response"""
        try:
            # Parse version information
            version_data = page_data.get('version', {})
            version = None
            if version_data:
                # Parse the 'when' timestamp
                when_str = version_data.get('when')
                when_datetime = None
                if when_str:
                    try:
                        # Handle ISO format with timezone
                        when_datetime = datetime.fromisoformat(when_str.replace('Z', '+00:00'))
                    except ValueError:
                        logger.warning(f"Could not parse timestamp: {when_str}")
                
                version = PageVersion(
                    number=version_data.get('number', 1),
                    when=when_datetime,
                    message=version_data.get('message'),
                    by=version_data.get('by')
                )
            
            return ConfluencePage(
                id=page_data['id'],
                type=page_data['type'],
                status=page_data['status'],
                title=page_data['title'],
                space=page_data.get('space'),
                version=version,
                body=page_data.get('body')
            )
            
        except Exception as e:
            logger.error(f"Failed to parse page data: {e}")
            return None

"""
Content processor for Confluence content
"""
import re
from typing import Dict, List, Optional, Any
import logging

from ..models.config_models import Config

logger = logging.getLogger(__name__)


class ContentProcessor:
    """Processes Confluence content for ingestion into Bedrock"""
    
    def __init__(self, config: Config):
        self.config = config
        self.confluence_base_url = config.confluence_base_url
    
    def process_confluence_content(self, storage_content: str, page_id: str, attachments: List[Dict[str, Any]] = None) -> str:
        """Process Confluence storage format content for Bedrock ingestion"""
        if not storage_content:
            return ""
        
        try:
            # Process images and attachments
            processed_content = self._process_images(storage_content, page_id, attachments or [])
            
            # Process links
            processed_content = self._process_links(processed_content)
            
            # Process macros
            processed_content = self._process_macros(processed_content)
            
            # Convert to clean text while preserving structure
            processed_content = self._convert_to_clean_text(processed_content)
            
            return processed_content
            
        except Exception as e:
            logger.error(f"Failed to process content for page {page_id}: {e}")
            # Return raw content as fallback
            return self._strip_html_tags(storage_content)
    
    def _process_images(self, content: str, page_id: str, attachments: List[Dict[str, Any]]) -> str:
        """Process image tags to preserve image references"""
        # Create a lookup dictionary for attachments by filename
        attachment_lookup = {}
        for attachment in attachments:
            filename = attachment.get('title', '')
            if filename:
                attachment_lookup[filename] = attachment
        
        logger.debug(f"Processing images for page {page_id}, found {len(attachments)} attachments")
        
        # Process ac:image tags with ri:attachment
        def replace_image_tag(match):
            full_tag = match.group(0)
            
            # Extract filename from ri:filename attribute
            filename_match = re.search(r'ri:filename="([^"]+)"', full_tag)
            if not filename_match:
                return full_tag
            
            filename = filename_match.group(1)
            
            # Check for S3 URI (already processed by image processor)
            s3_uri_match = re.search(r'ri:s3-uri="([^"]+)"', full_tag)
            if s3_uri_match:
                s3_uri = s3_uri_match.group(1)
                logger.debug(f"Found S3 reference for {filename}: {s3_uri}")
                return f"![{filename}]({s3_uri})"
            
            # Check if we have this attachment in our list
            attachment_info = attachment_lookup.get(filename)
            
            if attachment_info:
                # Use the download link from the attachment info if available
                download_link = attachment_info.get('_links', {}).get('download')
                if download_link:
                    image_url = f"{self.confluence_base_url}{download_link}"
                else:
                    image_url = f"{self.confluence_base_url}/wiki/download/attachments/{page_id}/{filename}"
                
                # Get additional info from attachment
                media_type = attachment_info.get('extensions', {}).get('mediaType', '')
                file_size = attachment_info.get('extensions', {}).get('fileSize', 0)
                
                logger.info(f"Found attachment: {filename} ({media_type}, {file_size} bytes)")
            else:
                # Attachment not found in API response, use fallback URL
                image_url = f"{self.confluence_base_url}/wiki/download/attachments/{page_id}/{filename}"
                logger.warning(f"Attachment {filename} not found in API response, using fallback URL")
            
            # Return markdown-style image reference
            return f"![{filename}]({image_url})"
        
        # Pattern for ac:image tags containing ri:attachment
        image_pattern = r'<ac:image[^>]*>.*?<ri:attachment[^>]*ri:filename="[^"]*"[^>]*\s*/>.*?</ac:image>'
        content = re.sub(image_pattern, replace_image_tag, content, flags=re.DOTALL)
        
        # Pattern for standalone ri:attachment tags
        attachment_pattern = r'<ri:attachment[^>]*ri:filename="[^"]*"[^>]*\s*/>'
        content = re.sub(attachment_pattern, replace_image_tag, content)
        
        return content
    
    def _process_links(self, content: str) -> str:
        """Process link tags"""
        # Convert ac:link tags to markdown links
        def replace_link(match):
            full_tag = match.group(0)
            
            # Extract link text
            text_match = re.search(r'<ac:plain-text-link-body><!\[CDATA\[(.*?)\]\]></ac:plain-text-link-body>', full_tag)
            if text_match:
                link_text = text_match.group(1)
            else:
                # Try to extract from ri:page title
                page_match = re.search(r'ri:content-title="([^"]*)"', full_tag)
                link_text = page_match.group(1) if page_match else "Link"
            
            # Extract URL
            url_match = re.search(r'<ri:url[^>]*ri:value="([^"]*)"', full_tag)
            if url_match:
                url = url_match.group(1)
                return f"[{link_text}]({url})"
            
            # For internal page links, just return the text
            return link_text
        
        # Pattern for ac:link tags
        link_pattern = r'<ac:link[^>]*>.*?</ac:link>'
        content = re.sub(link_pattern, replace_link, content, flags=re.DOTALL)
        
        return content
    
    def _process_macros(self, content: str) -> str:
        """Process Confluence macros"""
        # Remove or convert common macros
        
        # Remove ac:structured-macro tags but keep their content
        def replace_macro(match):
            full_tag = match.group(0)
            
            # Extract macro name
            name_match = re.search(r'ac:name="([^"]*)"', full_tag)
            macro_name = name_match.group(1) if name_match else "unknown"
            
            # Extract body content if present
            body_match = re.search(r'<ac:rich-text-body>(.*?)</ac:rich-text-body>', full_tag, re.DOTALL)
            if body_match:
                return body_match.group(1)
            
            # For macros without body, return empty or a placeholder
            if macro_name in ['toc', 'children', 'info', 'note', 'warning']:
                return f"\n[{macro_name.upper()}]\n"
            
            return ""
        
        # Pattern for structured macros
        macro_pattern = r'<ac:structured-macro[^>]*>.*?</ac:structured-macro>'
        content = re.sub(macro_pattern, replace_macro, content, flags=re.DOTALL)
        
        return content
    
    def _convert_to_clean_text(self, content: str) -> str:
        """Convert HTML-like content to clean text while preserving structure"""
        # Convert common HTML tags to text equivalents
        
        # Headers
        content = re.sub(r'<h([1-6])[^>]*>(.*?)</h\1>', r'\n\2\n', content, flags=re.DOTALL)
        
        # Paragraphs
        content = re.sub(r'<p[^>]*>(.*?)</p>', r'\1\n\n', content, flags=re.DOTALL)
        
        # Lists
        content = re.sub(r'<ul[^>]*>', '\n', content)
        content = re.sub(r'</ul>', '\n', content)
        content = re.sub(r'<ol[^>]*>', '\n', content)
        content = re.sub(r'</ol>', '\n', content)
        content = re.sub(r'<li[^>]*>(.*?)</li>', r'- \1\n', content, flags=re.DOTALL)
        
        # Strong/Bold
        content = re.sub(r'<strong[^>]*>(.*?)</strong>', r'**\1**', content, flags=re.DOTALL)
        content = re.sub(r'<b[^>]*>(.*?)</b>', r'**\1**', content, flags=re.DOTALL)
        
        # Emphasis/Italic
        content = re.sub(r'<em[^>]*>(.*?)</em>', r'*\1*', content, flags=re.DOTALL)
        content = re.sub(r'<i[^>]*>(.*?)</i>', r'*\1*', content, flags=re.DOTALL)
        
        # Code
        content = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', content, flags=re.DOTALL)
        
        # Line breaks
        content = re.sub(r'<br[^>]*/?>', '\n', content)
        
        # Remove remaining HTML tags
        content = self._strip_html_tags(content)
        
        # Clean up whitespace
        content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)  # Multiple newlines to double
        content = re.sub(r'^\s+|\s+$', '', content)  # Trim
        
        return content
    
    def _strip_html_tags(self, content: str) -> str:
        """Remove HTML tags from content"""
        # Remove HTML tags
        content = re.sub(r'<[^>]+>', '', content)
        
        # Decode HTML entities
        content = content.replace('&lt;', '<')
        content = content.replace('&gt;', '>')
        content = content.replace('&amp;', '&')
        content = content.replace('&quot;', '"')
        content = content.replace('&#39;', "'")
        content = content.replace('&nbsp;', ' ')
        
        return content

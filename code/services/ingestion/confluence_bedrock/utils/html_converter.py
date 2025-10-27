"""
HTML converter for retrieved content
"""
import re
import os
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class HTMLConverter:
    """Converts retrieved content to HTML format with local image support"""
    
    def __init__(self, confluence_base_url: str):
        self.confluence_base_url = confluence_base_url
    
    def convert_retrieved_content_to_html(self, retrieved_content: str, metadata: Dict[str, Any] = None, 
                                        local_images_dir: str = None) -> str:
        """Convert retrieved content to HTML format with local images"""
        try:
            # Start with basic HTML structure
            html_content = self._create_html_structure(retrieved_content, metadata)
            
            # Process markdown-like formatting
            html_content = self._process_markdown_formatting(html_content)
            
            # Process image references (with local images support)
            html_content = self._process_image_references(html_content, local_images_dir)
            
            return html_content
            
        except Exception as e:
            logger.error(f"Failed to convert content to HTML: {e}")
            return self._create_fallback_html(retrieved_content, metadata)
    
    def extract_s3_image_references(self, content: str) -> List[Dict[str, str]]:
        """
        Extract S3 image references from retrieved content
        
        Args:
            content: Retrieved content that may contain S3 references
            
        Returns:
            List of dictionaries with S3 image info
        """
        s3_refs = []
        
        # Pattern 1: S3 references in processed content (XML format) - flexible attribute order
        # <ri:attachment ri:filename="filename.ext" ri:s3-uri="s3://bucket/path" />
        # or <ri:attachment ri:s3-uri="s3://bucket/path" ri:filename="filename.ext" />
        pattern1 = r'<ri:attachment[^>]*ri:filename="([^"]+)"[^>]*ri:s3-uri="([^"]+)"[^>]*/>'
        pattern1_alt = r'<ri:attachment[^>]*ri:s3-uri="([^"]+)"[^>]*ri:filename="([^"]+)"[^>]*/>'
        
        matches = re.finditer(pattern1, content)
        for match in matches:
            filename = match.group(1)
            s3_uri = match.group(2)
            s3_refs.append({
                'filename': filename,
                's3_uri': s3_uri,
                'original_tag': match.group(0)
            })
        
        # Try alternative pattern (s3-uri first, then filename)
        matches = re.finditer(pattern1_alt, content)
        for match in matches:
            s3_uri = match.group(1)
            filename = match.group(2)
            # Avoid duplicates
            if not any(ref['filename'] == filename and ref['s3_uri'] == s3_uri for ref in s3_refs):
                s3_refs.append({
                    'filename': filename,
                    's3_uri': s3_uri,
                    'original_tag': match.group(0)
                })
        
        # Pattern 2: Markdown-style S3 references
        # ![filename](s3://bucket/path)
        pattern2 = r'!\[([^\]]+)\]\((s3://[^)]+)\)'
        
        matches = re.finditer(pattern2, content)
        for match in matches:
            filename = match.group(1)
            s3_uri = match.group(2)
            s3_refs.append({
                'filename': filename,
                's3_uri': s3_uri,
                'original_tag': match.group(0)
            })
        
        logger.debug(f"Found {len(s3_refs)} S3 image references in content")
        return s3_refs
    
    def replace_s3_references_with_local_paths(self, content: str, local_images_dir: str) -> str:
        """
        Replace S3 references with local image paths
        
        Args:
            content: Content with S3 references
            local_images_dir: Directory containing local images (relative to HTML file)
            
        Returns:
            Content with local image references
        """
        if not local_images_dir:
            return content
        
        # Pattern 1: S3 references in XML format
        pattern1 = r'<ri:attachment\s+ri:filename="([^"]+)"\s+ri:s3-uri="([^"]+)"\s*/>'
        
        def replace_xml_with_local_image(match):
            filename = match.group(1)
            s3_uri = match.group(2)
            
            # Create local image path (relative to HTML file)
            local_image_path = f"{local_images_dir}/{filename}"
            
            # Determine if it's an image based on extension
            image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg'}
            file_ext = os.path.splitext(filename.lower())[1]
            
            if file_ext in image_extensions:
                # Create img tag for images
                return f'<img src="{local_image_path}" alt="{filename}" title="{filename}" style="max-width: 100%; height: auto;" onerror="this.style.display=\'none\'; this.nextSibling.style.display=\'inline\'"><span style="display:none; color: #666; font-style: italic;">[Image: {filename} - Could not load]</span>'
            else:
                # Create link for other file types
                return f'<a href="{local_image_path}" target="_blank" title="Open {filename}">{filename}</a>'
        
        content = re.sub(pattern1, replace_xml_with_local_image, content)
        
        # Pattern 2: Markdown-style S3 references
        pattern2 = r'!\[([^\]]+)\]\((s3://[^)]+)\)'
        
        def replace_markdown_with_local_image(match):
            filename = match.group(1)
            s3_uri = match.group(2)
            
            # Create local image path (relative to HTML file)
            local_image_path = f"{local_images_dir}/{filename}"
            
            # Determine if it's an image based on extension
            image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg'}
            file_ext = os.path.splitext(filename.lower())[1]
            
            if file_ext in image_extensions:
                # Create img tag for images
                return f'<img src="{local_image_path}" alt="{filename}" title="{filename}" style="max-width: 100%; height: auto;" onerror="this.style.display=\'none\'; this.nextSibling.style.display=\'inline\'"><span style="display:none; color: #666; font-style: italic;">[Image: {filename} - Could not load]</span>'
            else:
                # Create link for other file types
                return f'<a href="{local_image_path}" target="_blank" title="Open {filename}">{filename}</a>'
        
        content = re.sub(pattern2, replace_markdown_with_local_image, content)
        
        return content
    
    def _create_html_structure(self, content: str, metadata: Dict[str, Any] = None) -> str:
        """Create basic HTML structure"""
        title = "Retrieved Content"
        if metadata and 'title' in metadata:
            title = metadata['title']
        
        # Create metadata section
        metadata_html = ""
        if metadata:
            metadata_html = self._create_metadata_section(metadata)
        
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            color: #333;
        }}
        .metadata {{
            background-color: #f5f5f5;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
            font-size: 0.9em;
        }}
        .metadata h3 {{
            margin-top: 0;
            color: #666;
        }}
        h1, h2, h3, h4, h5, h6 {{
            color: #2c3e50;
            margin-top: 1.5em;
            margin-bottom: 0.5em;
        }}
        code {{
            background-color: #f8f8f8;
            padding: 2px 4px;
            border-radius: 3px;
            font-family: 'Monaco', 'Consolas', monospace;
        }}
        pre {{
            background-color: #f8f8f8;
            padding: 15px;
            border-radius: 5px;
            overflow-x: auto;
        }}
        pre code {{
            background-color: transparent;
            padding: 0;
        }}
        img {{
            max-width: 100%;
            height: auto;
            border: 1px solid #ddd;
            border-radius: 5px;
            margin: 10px 0;
        }}
        .note {{
            background-color: #e8f4fd;
            border-left: 4px solid #2196F3;
            padding: 10px 15px;
            margin: 15px 0;
        }}
        .warning {{
            background-color: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 10px 15px;
            margin: 15px 0;
        }}
    </style>
</head>
<body>
    {metadata_html}
    <div class="content">
        {content}
    </div>
</body>
</html>"""
        
        return html
    
    def _create_metadata_section(self, metadata: Dict[str, Any]) -> str:
        """Create HTML metadata section"""
        metadata_items = []
        
        if 'title' in metadata:
            metadata_items.append(f"<strong>Title:</strong> {metadata['title']}")
        
        if 'source' in metadata:
            metadata_items.append(f"<strong>Source:</strong> {metadata['source']}")
        
        if 'page_id' in metadata:
            metadata_items.append(f"<strong>Page ID:</strong> {metadata['page_id']}")
        
        if 'url' in metadata:
            metadata_items.append(f"<strong>URL:</strong> <a href=\"{metadata['url']}\" target=\"_blank\">{metadata['url']}</a>")
        
        if 'last_modified' in metadata:
            metadata_items.append(f"<strong>Last Modified:</strong> {metadata['last_modified']}")
        
        if 'version' in metadata:
            metadata_items.append(f"<strong>Version:</strong> {metadata['version']}")
        
        if metadata_items:
            items_html = "<br>".join(metadata_items)
            return f"""<div class="metadata">
                <h3>Document Information</h3>
                {items_html}
            </div>"""
        
        return ""
    
    def _process_markdown_formatting(self, content: str) -> str:
        """Process markdown-like formatting in content"""
        # Headers
        content = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', content, flags=re.MULTILINE)
        content = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', content, flags=re.MULTILINE)
        content = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', content, flags=re.MULTILINE)
        content = re.sub(r'^#### (.*?)$', r'<h4>\1</h4>', content, flags=re.MULTILINE)
        content = re.sub(r'^##### (.*?)$', r'<h5>\1</h5>', content, flags=re.MULTILINE)
        content = re.sub(r'^###### (.*?)$', r'<h6>\1</h6>', content, flags=re.MULTILINE)
        
        # Bold and italic
        content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', content)
        content = re.sub(r'\*(.*?)\*', r'<em>\1</em>', content)
        
        # Code blocks
        content = re.sub(r'```(\w+)?\n(.*?)\n```', r'<pre><code class="language-\1">\2</code></pre>', content, flags=re.DOTALL)
        
        # Inline code
        content = re.sub(r'`([^`]+)`', r'<code>\1</code>', content)
        
        # Lists - fix the regex to handle multiple list items properly
        lines = content.split('\n')
        processed_lines = []
        in_list = False
        
        for line in lines:
            if line.strip().startswith('- '):
                if not in_list:
                    processed_lines.append('<ul>')
                    in_list = True
                list_item = line.strip()[2:]  # Remove '- '
                processed_lines.append(f'<li>{list_item}</li>')
            else:
                if in_list:
                    processed_lines.append('</ul>')
                    in_list = False
                processed_lines.append(line)
        
        if in_list:
            processed_lines.append('</ul>')
        
        content = '\n'.join(processed_lines)
        
        # Notes and warnings
        content = re.sub(r'\*\*Note:\*\* (.*?)(?=\n\n|\n$|$)', r'<div class="note"><strong>Note:</strong> \1</div>', content, flags=re.DOTALL)
        content = re.sub(r'\*\*Warning:\*\* (.*?)(?=\n\n|\n$|$)', r'<div class="warning"><strong>Warning:</strong> \1</div>', content, flags=re.DOTALL)
        
        # Paragraphs - improved logic
        paragraphs = content.split('\n\n')
        processed_paragraphs = []
        
        for para in paragraphs:
            para = para.strip()
            if para and not para.startswith('<') and not para.endswith('>'):
                # Only wrap in <p> if it's not already HTML
                para = f'<p>{para}</p>'
            if para:  # Only add non-empty paragraphs
                processed_paragraphs.append(para)
        
        content = '\n'.join(processed_paragraphs)
        
        return content
    
    def _process_image_references(self, content: str, local_images_dir: str = None) -> str:
        """Process image references and convert to HTML img tags"""
        
        # First, handle S3 references if local images directory is provided
        if local_images_dir:
            content = self.replace_s3_references_with_local_paths(content, local_images_dir)
        
        # Pattern for markdown-style images: ![alt text](url)
        def replace_image(match):
            alt_text = match.group(1)
            image_url = match.group(2)
            
            # If it's a Confluence attachment URL, provide better user experience
            if self.confluence_base_url in image_url:
                return f'''<div class="confluence-image-container" style="border: 1px dashed #ccc; padding: 15px; margin: 10px 0; background-color: #f9f9f9; border-radius: 5px;">
    <img src="{image_url}" alt="{alt_text}" title="{alt_text}" style="max-width: 100%; height: auto;" 
         onerror="this.style.display='none'; this.nextSibling.style.display='block'">
    <div style="display:none; text-align: center; color: #666; font-style: italic; padding: 10px;">
        <p><strong>🖼️ Image: {alt_text}</strong></p>
        <p>This image requires Confluence authentication to view.</p>
        <p><a href="{image_url}" target="_blank" style="color: #0052cc;">Click here to view in Confluence</a></p>
        <small>Note: You must be logged into Confluence to view this image.</small>
    </div>
</div>'''
            else:
                return f'<img src="{image_url}" alt="{alt_text}" title="{alt_text}" style="max-width: 100%; height: auto;" onerror="this.style.display=\'none\'; this.nextSibling.style.display=\'inline\'"><span style="display:none; color: #666; font-style: italic;">[Image: {alt_text} - Could not load]</span>'
        
        content = re.sub(r'!\[(.*?)\]\((.*?)\)', replace_image, content)
        
        return content
    
    def _create_fallback_html(self, content: str, metadata: Dict[str, Any] = None) -> str:
        """Create fallback HTML when processing fails"""
        title = "Retrieved Content"
        if metadata and 'title' in metadata:
            title = metadata['title']
        
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }}
        pre {{
            background-color: #f5f5f5;
            padding: 15px;
            border-radius: 5px;
            white-space: pre-wrap;
        }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <pre>{content}</pre>
</body>
</html>"""
    
    def save_html_file_with_images(self, html_content: str, output_dir: str, filename: str = None, 
                                 s3_service=None, s3_image_refs: List[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Save HTML content to file with local images
        
        Args:
            html_content: HTML content to save (should contain original content, not processed HTML)
            output_dir: Base output directory
            filename: HTML filename (optional)
            s3_service: S3 service for downloading images
            s3_image_refs: List of S3 image references to download
            
        Returns:
            Dictionary with file paths and download results
        """
        import os
        
        # Generate timestamp-based folder name
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_dir = os.path.join(output_dir, timestamp)
        images_dir = os.path.join(session_dir, "images")
        
        # Create directories
        os.makedirs(session_dir, exist_ok=True)
        os.makedirs(images_dir, exist_ok=True)
        
        # Download images if S3 service and references are provided
        download_results = []
        if s3_service and s3_image_refs:
            logger.info(f"Downloading {len(s3_image_refs)} images from S3...")
            
            for img_ref in s3_image_refs:
                try:
                    filename_only = img_ref['filename']
                    s3_uri = img_ref['s3_uri']
                    local_image_path = os.path.join(images_dir, filename_only)
                    
                    success = s3_service.download_attachment(s3_uri, local_image_path)
                    download_results.append({
                        'filename': filename_only,
                        's3_uri': s3_uri,
                        'local_path': local_image_path,
                        'success': success
                    })
                    
                    if success:
                        logger.info(f"✅ Downloaded: {filename_only}")
                    else:
                        logger.error(f"❌ Failed to download: {filename_only}")
                        
                except Exception as e:
                    logger.error(f"Error downloading {img_ref.get('filename', 'unknown')}: {e}")
                    download_results.append({
                        'filename': img_ref.get('filename', 'unknown'),
                        's3_uri': img_ref.get('s3_uri', ''),
                        'local_path': '',
                        'success': False,
                        'error': str(e)
                    })
        
        # Replace S3 references with local paths in HTML content AFTER downloading
        if s3_image_refs:
            logger.debug("Replacing S3 references with local image paths...")
            html_content = self.replace_s3_references_with_local_paths(html_content, "images")
        
        # Generate HTML filename
        if not filename:
            filename = "retrieved_content.html"
        
        if not filename.endswith('.html'):
            filename += '.html'
        
        html_filepath = os.path.join(session_dir, filename)
        
        # Save HTML file
        try:
            with open(html_filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            logger.info(f"Saved HTML file: {html_filepath}")
            
            # Summary
            successful_downloads = sum(1 for r in download_results if r['success'])
            total_images = len(download_results)
            
            return {
                'html_file': html_filepath,
                'session_dir': session_dir,
                'images_dir': images_dir,
                'download_results': download_results,
                'images_downloaded': successful_downloads,
                'total_images': total_images,
                'success': True
            }
            
        except Exception as e:
            logger.error(f"Failed to save HTML file: {e}")
            return {
                'html_file': None,
                'session_dir': session_dir,
                'images_dir': images_dir,
                'download_results': download_results,
                'success': False,
                'error': str(e)
            }

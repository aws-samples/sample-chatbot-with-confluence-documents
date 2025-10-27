"""
Crawler service that orchestrates the Confluence to Bedrock sync
"""
import os
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import logging

from ..models.config_models import Config
from ..models.confluence_models import ConfluencePage
from ..models.bedrock_models import BedrockDocument, BedrockMetadata, IngestResponse
from ..utils.content_processor import ContentProcessor
from ..utils.image_processor import ImageProcessor
from .confluence_service import ConfluenceService
from .bedrock_service import BedrockService
from .s3_service import S3Service

logger = logging.getLogger(__name__)


class CrawlerService:
    """Service that crawls Confluence and syncs to Bedrock Knowledge Base"""
    
    def __init__(self, config: Config):
        self.config = config
        self.confluence_service = ConfluenceService(config)
        self.bedrock_service = BedrockService(config)
        self.content_processor = ContentProcessor(config)
        
        # Initialize S3 service and image processor
        self.s3_service = S3Service(config)
        self.image_processor = ImageProcessor(config, self.s3_service)
        
        # Ensure output directory exists
        os.makedirs(config.output_dir, exist_ok=True)
    
    def crawl_and_sync(self) -> Dict[str, Any]:
        """Main method to crawl Confluence and sync to Bedrock"""
        logger.info("Starting Confluence to Bedrock sync...")
        
        # Get last crawl time
        last_crawl = self._get_last_crawl_time()
        is_first_crawl = last_crawl is None
        
        if is_first_crawl:
            logger.info("First crawl - will process all pages")
            pages_to_process = self.confluence_service.get_pages_in_space(self.config.confluence_space_key)
        else:
            logger.info(f"Incremental crawl - checking pages modified since {last_crawl}")
            pages_to_process = self._get_pages_modified_since(last_crawl)
        
        if not pages_to_process:
            logger.info("No pages to process")
            return {
                "status": "success",
                "pages_processed": 0,
                "is_first_crawl": is_first_crawl,
                "last_crawl": last_crawl
            }
        
        logger.info(f"Processing {len(pages_to_process)} pages")
        
        # Process pages and create Bedrock documents
        bedrock_documents = []
        processed_pages = []
        
        for page in pages_to_process:
            try:
                # Get full page content if not already expanded
                if not page.get_storage_content():
                    full_page = self.confluence_service.get_page_by_id(page.id)
                    if full_page:
                        page = full_page
                
                # Get page attachments
                logger.info(f"Fetching attachments for page: {page.title} (ID: {page.id})")
                attachments = self.confluence_service.get_page_attachments(page.id)
                
                if attachments:
                    logger.info(f"Found {len(attachments)} attachments for page {page.id}")
                    for attachment in attachments:
                        logger.debug(f"  - {attachment.get('title', 'Unknown')} ({attachment.get('extensions', {}).get('mediaType', 'Unknown type')})")
                else:
                    logger.debug(f"No attachments found for page {page.id}")
                
                # Process attachments and get modified content with S3 references
                page_content = page.get_storage_content() or ""
                attachment_errors = []
                
                if attachments and page_content:
                    try:
                        logger.info(f"Processing attachments for page {page.id}")
                        processing_result = self.image_processor.process_page_images(
                            page.id, page_content, attachments
                        )
                        
                        # Extract modified content and results
                        modified_content = processing_result['modified_content']
                        
                        # Log attachment processing results
                        successful = processing_result['successful_uploads']
                        total = processing_result['processed_images']
                        logger.info(f"Attachment processing: {successful}/{total} successful")
                        
                        # Collect errors for visible logging
                        for error in processing_result['errors']:
                            error_msg = f"Attachment processing error: {error}"
                            logger.error(f"🔴 ATTACHMENT ERROR: {error_msg}")
                            attachment_errors.append(error_msg)
                        
                        # Use modified content (with S3 references)
                        page_content = modified_content
                        
                        # Debug: Check if S3 URIs are in the content
                        if "ri:s3-uri=" in page_content:
                            logger.info(f"✅ Page {page.id} content includes S3 URIs")
                        else:
                            logger.warning(f"⚠️  Page {page.id} content does not include S3 URIs")
                        
                    except Exception as e:
                        error_msg = f"Failed to process attachments for page {page.id}: {e}"
                        logger.error(f"🔴 ATTACHMENT PROCESSING ERROR: {error_msg}")
                        attachment_errors.append(error_msg)
                        # Continue with original content
                
                # Process content (this should preserve S3 references and do other processing)
                processed_content = self.content_processor.process_confluence_content(
                    page_content,
                    page.id,
                    []  # Don't pass attachments to avoid re-processing images
                )
                
                # Create Bedrock document
                metadata = BedrockMetadata(
                    title=page.title,
                    page_id=page.id,
                    space_key=self.config.confluence_space_key,
                    version=page.version_number,
                    last_modified=page.last_modified_datetime.isoformat() if page.last_modified_datetime else None,
                    url=self._build_page_url(page.id)
                )
                
                bedrock_doc = BedrockDocument(
                    document_id=f"confluence-{page.id}",
                    content=processed_content,
                    metadata=metadata
                )
                
                bedrock_documents.append(bedrock_doc)
                processed_pages.append({
                    "page": page,
                    "attachment_errors": attachment_errors
                })
                
                logger.info(f"Prepared document for page: {page.title} (ID: {page.id})")
                
                # Log attachment errors prominently
                if attachment_errors:
                    logger.error(f"🔴 PAGE {page.id} HAD {len(attachment_errors)} ATTACHMENT ERRORS:")
                    for error in attachment_errors:
                        logger.error(f"🔴   {error}")
                
            except Exception as e:
                logger.error(f"Failed to process page {page.id} ({page.title}): {e}")
                continue
        
        # Ingest documents to Bedrock
        ingest_results = []
        if bedrock_documents:
            try:
                ingest_results = self.bedrock_service.ingest_documents(bedrock_documents)
                logger.info(f"Ingested {len(ingest_results)} documents to Bedrock")
            except Exception as e:
                logger.error(f"Failed to ingest documents to Bedrock: {e}")
                return {
                    "status": "error",
                    "error": str(e),
                    "pages_processed": 0,
                    "is_first_crawl": is_first_crawl
                }
        
        # Update last crawl time
        current_time = datetime.now(timezone.utc)
        self._save_last_crawl_time(current_time)
        
        # Prepare results
        successful_ingests = [r for r in ingest_results if r.status in ['STARTING', 'PENDING', 'IN_PROGRESS', 'INDEXED']]
        failed_ingests = [r for r in ingest_results if r.status in ['FAILED', 'IGNORED']]
        
        # Collect all attachment errors
        all_attachment_errors = []
        for page_info in processed_pages:
            if page_info["attachment_errors"]:
                all_attachment_errors.extend(page_info["attachment_errors"])
        
        result = {
            "status": "success",
            "pages_processed": len(processed_pages),
            "documents_ingested": len(successful_ingests),
            "failed_ingests": len(failed_ingests),
            "is_first_crawl": is_first_crawl,
            "last_crawl": last_crawl,
            "current_crawl": current_time,
            "processed_pages": [{"id": p["page"].id, "title": p["page"].title} for p in processed_pages],
            "ingest_results": [{"document_id": r.document_id, "status": r.status} for r in ingest_results],
            "attachment_errors": all_attachment_errors
        }
        
        if failed_ingests:
            logger.warning(f"{len(failed_ingests)} documents failed to ingest")
            result["failed_documents"] = [{"document_id": r.document_id, "status": r.status, "reason": r.status_reason} for r in failed_ingests]
        
        if all_attachment_errors:
            logger.error(f"🔴 TOTAL ATTACHMENT ERRORS: {len(all_attachment_errors)}")
            for error in all_attachment_errors:
                logger.error(f"🔴   {error}")
        
        logger.info(f"Sync completed successfully. Processed {len(processed_pages)} pages, ingested {len(successful_ingests)} documents")
        return result
    
    def _get_last_crawl_time(self) -> Optional[datetime]:
        """Get the last crawl time from file"""
        last_crawl_path = os.path.join(self.config.output_dir, self.config.last_crawl_file)
        
        if not os.path.exists(last_crawl_path):
            return None
        
        try:
            with open(last_crawl_path, 'r', encoding='utf-8') as f:
                timestamp_str = f.read().strip()
                return datetime.fromisoformat(timestamp_str)
        except Exception as e:
            logger.error(f"Failed to read last crawl time: {e}")
            return None
    
    def _save_last_crawl_time(self, crawl_time: datetime) -> None:
        """Save the last crawl time to file"""
        last_crawl_path = os.path.join(self.config.output_dir, self.config.last_crawl_file)
        
        try:
            with open(last_crawl_path, 'w', encoding='utf-8') as f:
                f.write(crawl_time.isoformat())
            logger.info(f"Saved last crawl time: {crawl_time}")
        except Exception as e:
            logger.error(f"Failed to save last crawl time: {e}")
    
    def get_sync_status(self) -> Dict[str, Any]:
        """Get current sync status"""
        last_crawl = self._get_last_crawl_time()
        
        # Get space info
        space_info = self.confluence_service.get_space_info(self.config.confluence_space_key)
        
        # Get knowledge base info
        kb_info = self.bedrock_service.get_knowledge_base_info()
        
        return {
            "last_crawl": last_crawl,
            "space_info": {
                "key": space_info.key if space_info else None,
                "name": space_info.name if space_info else None
            },
            "knowledge_base_id": self.config.knowledge_base_id,
            "knowledge_base_status": kb_info.get('status') if kb_info else None
        }
    
    def _get_pages_modified_since(self, since_date: datetime) -> List[ConfluencePage]:
        """Get pages modified since a specific date"""
        # Get all pages and filter by modification date
        all_pages = self.confluence_service.get_pages_in_space(self.config.confluence_space_key)
        
        modified_pages = []
        for page in all_pages:
            if page.has_changed_since(since_date):
                modified_pages.append(page)
        
        logger.info(f"Found {len(modified_pages)} pages modified since {since_date}")
        return modified_pages
    
    def _build_page_url(self, page_id: str) -> str:
        """Build URL for a Confluence page"""
        return f"{self.config.get_confluence_base_url()}/wiki/spaces/{self.config.confluence_space_key}/pages/{page_id}"

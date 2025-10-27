"""
Lambda handler for Confluence to Bedrock ingestion
"""
import json
import logging
import os
import boto3
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS clients
ssm = boto3.client('ssm')
secrets_manager = boto3.client('secretsmanager')


class SSMCrawlTracker:
    """Tracks crawl state in SSM Parameter Store using JSON"""
    
    def __init__(self, parameter_name: str):
        self.parameter_name = parameter_name
    
    def _retry_ssm_operation(self, operation, max_retries=3):
        """Retry SSM operations with exponential backoff"""
        for attempt in range(max_retries):
            try:
                return operation()
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                wait_time = (2 ** attempt) * 0.5
                logger.warning(f"SSM operation failed (attempt {attempt + 1}), retrying in {wait_time}s: {e}")
                time.sleep(wait_time)
    
    def _get_crawl_state(self) -> Dict[str, Any]:
        """Get current crawl state from SSM"""
        def get_param():
            try:
                response = ssm.get_parameter(Name=self.parameter_name, WithDecryption=True)
                return json.loads(response['Parameter']['Value'])
            except ssm.exceptions.ParameterNotFound:
                return {}
        
        return self._retry_ssm_operation(get_param)
    
    def _save_crawl_state(self, state: Dict[str, Any]) -> None:
        """Save crawl state to SSM"""
        def put_param():
            # Get parameter metadata to retrieve KMS key ID
            param_info = ssm.describe_parameters(
                Filters=[{'Key': 'Name', 'Values': [self.parameter_name]}]
            )
            
            # Prepare put_parameter arguments
            put_params = {
                'Name': self.parameter_name,
                'Value': json.dumps(state),
                'Type': 'SecureString',
                'Overwrite': True
            }
            
            # Add KMS key ID if parameter uses one
            if param_info['Parameters'] and 'KeyId' in param_info['Parameters'][0]:
                put_params['KeyId'] = param_info['Parameters'][0]['KeyId']
            
            ssm.put_parameter(**put_params)
        
        self._retry_ssm_operation(put_param)
    
    def get_last_crawl_time(self, space_key: str) -> Optional[datetime]:
        """Get last crawl time for a space"""
        try:
            state = self._get_crawl_state()
            space_data = state.get(space_key, {})
            timestamp_str = space_data.get('last_crawl_time')
            
            if timestamp_str:
                return datetime.fromisoformat(timestamp_str)
                
        except Exception as e:
            logger.error(f"Failed to get last crawl time for {space_key}: {e}")
        
        return None
    
    def save_last_crawl_time(self, space_key: str, crawl_time: datetime) -> None:
        """Save last crawl time for a space"""
        try:
            state = self._get_crawl_state()
            state[space_key] = {
                'last_crawl_time': crawl_time.isoformat(),
                'updated_at': datetime.now(timezone.utc).isoformat()
            }
            
            self._save_crawl_state(state)
            logger.info(f"Saved last crawl time for {space_key}: {crawl_time}")
            
        except Exception as e:
            logger.error(f"Failed to save last crawl time for {space_key}: {e}")


def load_configuration() -> Dict[str, Any]:
    """Load configuration from SSM Parameter Store"""
    try:
        parameter_name = os.environ['CONFIG_PARAMETER']
        response = ssm.get_parameter(Name=parameter_name, WithDecryption=True)
        config = json.loads(response['Parameter']['Value'])
        
        # Load Confluence token from Secrets Manager
        secret_arn = os.environ['CONFLUENCE_SECRET_ARN']
        secret_response = secrets_manager.get_secret_value(SecretId=secret_arn)
        secret_data = json.loads(secret_response['SecretString'])
        config['confluence_api_token'] = secret_data['token']
        
        # Add environment variables
        config['s3_attachments_path'] = f"s3://{os.environ['ATTACHMENTS_BUCKET']}/attachments/"
        config['aws_region'] = os.environ.get('AWS_REGION')
        if not config['aws_region']:
            # Use boto3 session region as fallback
            session = boto3.Session()
            config['aws_region'] = session.region_name
            if not config['aws_region']:
                raise ValueError("AWS region not found in environment variable AWS_REGION and no default region configured in boto3 session.")
        
        return config
    except Exception as e:
        logger.warning(f"Failed to load configuration: {e}")
        raise


def create_config_object(config_dict: Dict[str, Any]) -> Any:
    """Create a Config object from dictionary (simplified version)"""
    class SimpleConfig:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)
        
        def get_confluence_base_url(self):
            return self.confluence_base_url.rstrip('/')
    
    return SimpleConfig(**config_dict)


def process_space_incrementally(space_key: str, config: Any, crawler_tracker: SSMCrawlTracker) -> Dict[str, Any]:
    """Process a single space incrementally"""
    from confluence_bedrock.services.confluence_service import ConfluenceService
    from confluence_bedrock.services.bedrock_service import BedrockService
    from confluence_bedrock.services.s3_service import S3Service
    from confluence_bedrock.utils.content_processor import ContentProcessor
    from confluence_bedrock.utils.image_processor import ImageProcessor
    from confluence_bedrock.models.bedrock_models import BedrockDocument, BedrockMetadata
    
    logger.info(f"Processing space: {space_key}")
    
    # Initialize services
    confluence_service = ConfluenceService(config)
    bedrock_service = BedrockService(config)
    s3_service = S3Service(config)
    content_processor = ContentProcessor(config)
    image_processor = ImageProcessor(config, s3_service)
    
    # Get last crawl time
    last_crawl = crawler_tracker.get_last_crawl_time(space_key)
    is_first_crawl = last_crawl is None
    
    if is_first_crawl:
        logger.info(f"First crawl for space {space_key} - will process all pages")
        pages_to_process = confluence_service.get_pages_in_space(space_key)
    else:
        logger.info(f"Incremental crawl for space {space_key} - checking pages modified since {last_crawl}")
        all_pages = confluence_service.get_pages_in_space(space_key)
        pages_to_process = [page for page in all_pages if page.has_changed_since(last_crawl)]
    
    if not pages_to_process:
        logger.info(f"No pages to process for space {space_key}")
        return {"status": "success", "pages_processed": 0, "space_key": space_key}
    
    # Sort pages by modification date (oldest first) for resumable processing
    pages_to_process.sort(key=lambda p: p.last_modified_datetime or datetime.min.replace(tzinfo=timezone.utc))
    
    logger.info(f"Processing {len(pages_to_process)} pages for space {space_key}")
    
    processed_count = 0
    current_time = datetime.now(timezone.utc)
    
    # Process pages one by one with state updates
    for page in pages_to_process:
        try:
            # Get full page content
            if not page.get_storage_content():
                full_page = confluence_service.get_page_by_id(page.id)
                if full_page:
                    page = full_page
            
            # Get attachments and process images
            attachments = confluence_service.get_page_attachments(page.id)
            page_content = page.get_storage_content() or ""
            
            if attachments and page_content:
                try:
                    processing_result = image_processor.process_page_images(
                        page.id, page_content, attachments
                    )
                    page_content = processing_result['modified_content']
                except Exception as e:
                    logger.error(f"Image processing failed for page {page.id}: {e}")
            
            # Process content for Bedrock
            processed_content = content_processor.process_confluence_content(
                page_content, page.id, []
            )
            
            # Create and ingest Bedrock document
            metadata = BedrockMetadata(
                title=page.title,
                page_id=page.id,
                space_key=space_key,
                version=page.version_number,
                last_modified=page.last_modified_datetime.isoformat() if page.last_modified_datetime else None,
                url=f"{config.get_confluence_base_url()}/wiki/spaces/{space_key}/pages/{page.id}"
            )
            
            bedrock_doc = BedrockDocument(
                document_id=f"confluence-{page.id}",
                content=processed_content,
                metadata=metadata
            )
            
            # Ingest single document
            ingest_results = bedrock_service.ingest_documents([bedrock_doc])
            
            if ingest_results and ingest_results[0].status not in ['FAILED', 'IGNORED']:
                processed_count += 1
                logger.info(f"Successfully processed page {page.id}: {page.title}")
                
                # Update crawl time after each successful page (for resumability)
                page_time = page.last_modified_datetime or current_time
                crawler_tracker.save_last_crawl_time(space_key, page_time)
            else:
                logger.error(f"Failed to ingest page {page.id}: {page.title}")
                
        except Exception as e:
            logger.error(f"Failed to process page {page.id}: {e}")
            continue
    
    # Final crawl time update
    crawler_tracker.save_last_crawl_time(space_key, current_time)
    
    return {
        "status": "success",
        "space_key": space_key,
        "pages_processed": processed_count,
        "is_first_crawl": is_first_crawl,
        "total_pages_found": len(pages_to_process)
    }


def lambda_handler(event, context):
    """Main Lambda handler"""
    try:
        # Load configuration
        config_dict = load_configuration()
        config = create_config_object(config_dict)
        
        # Initialize SSM tracker
        crawl_state_parameter = os.environ['CRAWL_STATE_PARAMETER']
        crawler_tracker = SSMCrawlTracker(crawl_state_parameter)
        
        # Get spaces to process from config
        spaces = config_dict.get('confluence_spaces', [])
        if not spaces:
            logger.warning("No Confluence spaces configured")
            return {"statusCode": 200, "body": json.dumps({"status": "no_spaces_configured"})}
        
        results = []
        
        # Process each space
        for space_config in spaces:
            space_key = space_config.get('key') or space_config.get('name')
            if not space_key:
                logger.error(f"Invalid space configuration: {space_config}")
                continue
            
            # Update config for this space
            config.confluence_space_key = space_key
            
            try:
                result = process_space_incrementally(space_key, config, crawler_tracker)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to process space {space_key}: {e}")
                results.append({
                    "status": "error",
                    "space_key": space_key,
                    "error": str(e)
                })
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "status": "completed",
                "results": results,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        }
        
    except Exception as e:
        logger.error(f"Lambda execution failed: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        }

"""
Bedrock Knowledge Base service
"""
import boto3
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime

from ..models.bedrock_models import BedrockDocument, IngestResponse
from ..models.config_models import Config

logger = logging.getLogger(__name__)


class BedrockService:
    """Service for interacting with Bedrock Knowledge Base"""
    
    def __init__(self, config: Config):
        self.config = config
        self.bedrock_client = boto3.client('bedrock-agent', region_name=config.aws_region)
        self.bedrock_runtime_client = boto3.client('bedrock-agent-runtime', region_name=config.aws_region)
    
    def ingest_documents(self, documents: List[BedrockDocument]) -> List[IngestResponse]:
        """Ingest multiple documents into the knowledge base"""
        if not documents:
            logger.warning("No documents to ingest")
            return []
        
        # Convert documents to Bedrock format
        bedrock_documents = [doc.to_bedrock_format() for doc in documents]
        
        try:
            logger.info(f"Ingesting {len(bedrock_documents)} documents into knowledge base")
            
            response = self.bedrock_client.ingest_knowledge_base_documents(
                knowledgeBaseId=self.config.knowledge_base_id,
                dataSourceId=self.config.data_source_id,
                documents=bedrock_documents
            )
            
            # Parse response
            ingest_responses = []
            for item in response.get('documentDetails', []):
                ingest_response = IngestResponse.from_bedrock_response(item)
                ingest_responses.append(ingest_response)
                logger.info(f"Document {ingest_response.document_id}: {ingest_response.status}")
            
            return ingest_responses
            
        except Exception as e:
            logger.warning(f"Failed to ingest documents: {e}")
            raise
    
    def ingest_single_document(self, document: BedrockDocument) -> Optional[IngestResponse]:
        """Ingest a single document"""
        responses = self.ingest_documents([document])
        return responses[0] if responses else None
    
    def retrieve_documents(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Retrieve documents from the knowledge base"""
        try:
            logger.info(f"Retrieving documents for query: '{query}'")
            
            response = self.bedrock_runtime_client.retrieve(
                knowledgeBaseId=self.config.knowledge_base_id,
                retrievalQuery={
                    'text': query
                },
                retrievalConfiguration={
                    'vectorSearchConfiguration': {
                        'numberOfResults': max_results
                    }
                }
            )
            
            results = response.get('retrievalResults', [])
            logger.info(f"Retrieved {len(results)} documents")
            
            return results
            
        except Exception as e:
            logger.warning(f"Failed to retrieve documents: {e}")
            raise
    
    def delete_document(self, document_id: str) -> bool:
        """Delete a document from the knowledge base"""
        try:
            # Note: Bedrock doesn't have a direct delete API for custom data sources
            # We need to re-ingest with empty content or use a different approach
            # For now, we'll log this limitation
            logger.warning(f"Delete operation not directly supported for document {document_id}")
            logger.warning("To remove a document, re-ingest with updated content or recreate the data source")
            return False
            
        except Exception as e:
            logger.error(f"Failed to delete document {document_id}: {e}")
            return False
    
    def get_knowledge_base_info(self) -> Optional[Dict[str, Any]]:
        """Get information about the knowledge base"""
        try:
            response = self.bedrock_client.get_knowledge_base(
                knowledgeBaseId=self.config.knowledge_base_id
            )
            return response.get('knowledgeBase')
            
        except Exception as e:
            logger.error(f"Failed to get knowledge base info: {e}")
            return None
    
    def get_data_source_info(self) -> Optional[Dict[str, Any]]:
        """Get information about the data source"""
        try:
            response = self.bedrock_client.get_data_source(
                knowledgeBaseId=self.config.knowledge_base_id,
                dataSourceId=self.config.data_source_id
            )
            return response.get('dataSource')
            
        except Exception as e:
            logger.error(f"Failed to get data source info: {e}")
            return None

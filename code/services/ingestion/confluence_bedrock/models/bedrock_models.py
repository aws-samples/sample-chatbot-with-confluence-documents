"""
Bedrock data models
"""
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from datetime import datetime


@dataclass
class BedrockMetadata:
    """Metadata for Bedrock documents"""
    title: str
    page_id: str
    space_key: str
    version: int
    last_modified: Optional[str] = None
    url: Optional[str] = None
    source: str = "confluence"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Bedrock API"""
        return {
            'title': self.title,
            'page_id': self.page_id,
            'space_key': self.space_key,
            'version': float(self.version),
            'last_modified': self.last_modified,
            'url': self.url,
            'source': self.source
        }


@dataclass
class BedrockDocument:
    """Document for Bedrock ingestion"""
    document_id: str
    content: str
    metadata: BedrockMetadata
    
    def to_bedrock_format(self) -> Dict[str, Any]:
        """Convert to Bedrock API format"""
        inline_attributes = []
        for key, value in self.metadata.to_dict().items():
            if value is not None:
                if isinstance(value, str):
                    value_dict = {'type': 'STRING', 'stringValue': value}
                else:
                    value_dict = {'type': 'NUMBER', 'numberValue': value}
                
                inline_attributes.append({
                    'key': key,
                    'value': value_dict
                })
        
        return {
            'content': {
                'dataSourceType': 'CUSTOM',
                'custom': {
                    'customDocumentIdentifier': {
                        'id': self.document_id
                    },
                    'sourceType': 'IN_LINE',
                    'inlineContent': {
                        'type': 'TEXT',
                        'textContent': {
                            'data': self.content
                        }
                    }
                }
            },
            'metadata': {
                'type': 'IN_LINE_ATTRIBUTE',
                'inlineAttributes': inline_attributes
            }
        }


@dataclass
class IngestResponse:
    """Response from Bedrock document ingestion"""
    document_id: str
    status: str
    status_reason: Optional[str] = None
    updated_at: Optional[datetime] = None
    
    @classmethod
    def from_bedrock_response(cls, response_item: Dict[str, Any]) -> "IngestResponse":
        """Create from Bedrock API response"""
        identifier = response_item.get('identifier', {})
        document_id = identifier.get('custom', {}).get('id', 'unknown')
        
        updated_at = None
        if 'updatedAt' in response_item:
            updated_at = response_item['updatedAt']
            if isinstance(updated_at, str):
                try:
                    updated_at = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                except ValueError:
                    updated_at = None
        
        return cls(
            document_id=document_id,
            status=response_item.get('status', 'UNKNOWN'),
            status_reason=response_item.get('statusReason'),
            updated_at=updated_at
        )

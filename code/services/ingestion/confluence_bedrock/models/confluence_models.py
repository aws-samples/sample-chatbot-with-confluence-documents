"""
Confluence data models
"""
from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime


@dataclass
class PageVersion:
    """Confluence page version information"""
    number: int
    when: datetime
    message: Optional[str] = None
    by: Optional[Dict[str, Any]] = None


@dataclass
class ConfluenceSpace:
    """Confluence space information"""
    id: str
    key: str
    name: str
    type: str
    status: str


@dataclass
class ConfluencePage:
    """Confluence page information"""
    id: str
    type: str
    status: str
    title: str
    space: Optional[Dict[str, Any]] = None
    version: Optional[PageVersion] = None
    body: Optional[Dict[str, Any]] = None
    
    def get_storage_content(self) -> Optional[str]:
        """Get storage format content from page body"""
        if self.body and 'storage' in self.body:
            return self.body['storage'].get('value')
        return None
    
    @property
    def version_number(self) -> int:
        """Get version number"""
        return self.version.number if self.version else 1
    
    @property
    def last_modified_datetime(self) -> Optional[datetime]:
        """Get last modified datetime"""
        return self.version.when if self.version else None
    
    def has_changed_since(self, since_date: datetime) -> bool:
        """Check if page has changed since given date"""
        if not self.version or not self.version.when:
            return True  # Assume changed if no version info
        
        return self.version.when > since_date

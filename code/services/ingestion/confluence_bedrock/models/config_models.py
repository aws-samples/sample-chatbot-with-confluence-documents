"""
Configuration models
"""
import json
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    """Configuration for Confluence to Bedrock integration"""
    
    # Confluence settings
    confluence_base_url: str
    confluence_email: str
    confluence_api_token: str
    confluence_space_key: str
    confluence_api_token_file: str
    
    # AWS/Bedrock settings
    aws_region: str
    aws_account_id: str
    knowledge_base_id: str
    data_source_id: str
    
    # S3 settings for attachments
    s3_attachments_path: str
    
    # Application settings
    last_crawl_file: str = "last_crawl.txt"
    output_dir: str = "output"
    log_level: str = "INFO"
    request_timeout: int = 30
    max_retries: int = 3
    
    def __post_init__(self):
        """Validate configuration after initialization"""
        # Validate log level
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if self.log_level.upper() not in valid_levels:
            raise ValueError(f'log_level must be one of {valid_levels}')
        self.log_level = self.log_level.upper()
        
        # Validate AWS account ID
        if not (len(self.aws_account_id) == 12 and self.aws_account_id.isdigit()):
            raise ValueError("aws_account_id must be a 12-digit number")
        
        # Validate required fields
        required_fields = [
            'confluence_base_url', 'confluence_email', 'confluence_space_key',
            'aws_region', 'knowledge_base_id', 'data_source_id', 's3_attachments_path'
        ]
        for field in required_fields:
            if not getattr(self, field):
                raise ValueError(f"Required field '{field}' is empty")
    
    @classmethod
    def from_file(cls, config_file: str) -> "Config":
        """Load configuration from JSON file"""
        if not os.path.exists(config_file):
            raise FileNotFoundError(f"Configuration file not found: {config_file}")
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # Flatten the nested structure
            flattened_config = {
                # Confluence settings
                'confluence_base_url': config_data['confluence']['base_url'],
                'confluence_email': config_data['confluence']['email'],
                'confluence_space_key': config_data['confluence']['space_key'],
                'confluence_api_token_file': config_data['confluence']['api_token_file'],
                'confluence_api_token': '',  # Will be loaded from file
                
                # AWS settings
                'aws_region': config_data['aws']['region'],
                'aws_account_id': config_data['aws']['account_id'],
                
                # Bedrock settings
                'knowledge_base_id': config_data['bedrock']['knowledge_base_id'],
                'data_source_id': config_data['bedrock']['data_source_id'],
                
                # S3 settings
                's3_attachments_path': config_data.get('s3', {}).get('attachments_path', ''),
                
                # Application settings
                'last_crawl_file': config_data['application'].get('last_crawl_file', 'last_crawl.txt'),
                'output_dir': config_data['application'].get('output_dir', 'output'),
                'log_level': config_data['application'].get('log_level', 'INFO'),
                'request_timeout': config_data['application'].get('request_timeout', 30),
                'max_retries': config_data['application'].get('max_retries', 3),
            }
            
            # Create config instance
            config = cls(**flattened_config)
            
            # Load API token from file
            config.load_api_token()
            
            return config
            
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in configuration file: {e}")
        except KeyError as e:
            raise ValueError(f"Missing required configuration key: {e}")
        except Exception as e:
            raise ValueError(f"Error loading configuration: {e}")
    
    def load_api_token(self) -> None:
        """Load API token from file"""
        token_path = self.confluence_api_token_file
        
        # Handle relative paths
        if not os.path.isabs(token_path):
            # Make it relative to the current working directory (where the script is run)
            token_path = os.path.abspath(token_path)
        
        if not os.path.exists(token_path):
            raise FileNotFoundError(f"API token file not found: {token_path}")
        
        try:
            with open(token_path, 'r', encoding='utf-8') as f:
                self.confluence_api_token = f.read().strip()
            
            if not self.confluence_api_token:
                raise ValueError("API token file is empty")
                
        except Exception as e:
            raise ValueError(f"Error loading API token from {token_path}: {e}")
    
    def save_to_file(self, config_file: str) -> None:
        """Save configuration to JSON file (excluding sensitive data)"""
        config_data = {
            "confluence": {
                "base_url": self.confluence_base_url,
                "email": self.confluence_email,
                "space_key": self.confluence_space_key,
                "api_token_file": self.confluence_api_token_file
            },
            "aws": {
                "region": self.aws_region,
                "account_id": self.aws_account_id
            },
            "bedrock": {
                "knowledge_base_id": self.knowledge_base_id,
                "data_source_id": self.data_source_id
            },
            "s3": {
                "attachments_path": self.s3_attachments_path
            },
            "application": {
                "last_crawl_file": self.last_crawl_file,
                "output_dir": self.output_dir,
                "log_level": self.log_level,
                "request_timeout": self.request_timeout,
                "max_retries": self.max_retries
            }
        }
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2)
    
    def get_confluence_base_url(self) -> str:
        """Get Confluence base URL without trailing slash"""
        return self.confluence_base_url.rstrip('/')
    
    def get_full_output_path(self, filename: str) -> str:
        """Get full path for output file"""
        return os.path.join(self.output_dir, filename)
    
    def validate_aws_config(self) -> bool:
        """Validate AWS configuration"""
        # Basic validation - could be extended
        return (
            len(self.aws_account_id) == 12 and 
            self.aws_account_id.isdigit() and
            len(self.aws_region) > 0
        )

import boto3
import json
import uuid
import os
import re
from typing import Dict, Any

class AgentCoreClient:
    def __init__(self):
        self.client = None
        self.agent_arn = None
        self.memory_id = None
        self.region = None
        self._load_agentcore_config()
    
    def _parse_region_from_arn(self, arn: str) -> str:
        """Extract region from ARN format: arn:aws:service:region:account:resource"""
        try:
            parts = arn.split(':')
            if len(parts) >= 4:
                return parts[3]
        except Exception as e:
            print(f"Warning: Could not parse region from ARN '{arn}': {e}")
        return None
    
    def _load_agentcore_config(self):
        """Load AgentCore configuration from SSM Parameter Store"""
        try:
            # Get SSM parameter ARN from environment variable
            ssm_parameter_arn = os.environ.get('AGENTCORE_SSM_PARAMETER_ARN')
            
            if ssm_parameter_arn:
                # Parse region from SSM parameter ARN
                self.region = self._parse_region_from_arn(ssm_parameter_arn)
                # Extract parameter name from ARN (everything after 'parameter/')
                if 'parameter/' in ssm_parameter_arn:
                    parameter_name = '/' + ssm_parameter_arn.split('parameter/')[-1]
                else:
                    # If it's not an ARN, treat it as parameter name directly
                    parameter_name = ssm_parameter_arn
            else:
                # Fallback: use boto3 session region and default parameter name
                boto_session = boto3.Session()
                self.region = boto_session.region_name
                if not self.region:
                    raise ValueError("No AWS region found. Please configure AWS CLI with default region or set AGENTCORE_SSM_PARAMETER_ARN environment variable.")
                parameter_name = '/confluence-bedrock/dev/config'
                print(f"No AGENTCORE_SSM_PARAMETER_ARN found, using default: {parameter_name} in region {self.region}")
            
            # Create SSM client with determined region
            ssm_client = boto3.client('ssm', region_name=self.region)
            
            # Get SSM parameter
            response = ssm_client.get_parameter(Name=parameter_name, WithDecryption=True)
            config = json.loads(response['Parameter']['Value'])
            
            # Extract AgentCore configuration
            self.agent_arn = config.get('agent_arn')
            self.memory_id = config.get('memory_id')
            
            if self.agent_arn:
                # Create bedrock-agentcore client with correct region
                self.client = boto3.client('bedrock-agentcore', region_name=self.region)
                print(f"Loaded AgentCore config from SSM: agent_arn={self.agent_arn}, memory_id={self.memory_id}, region={self.region}")
            else:
                print("No agent_arn found in SSM parameter. AgentCore may not be deployed yet.")
                
        except Exception as e:
            print(f"Could not load AgentCore config from SSM: {e}")
            print("Falling back to YAML file...")
            self._load_agent_arn_from_yaml()
    
    def _load_agent_arn_from_yaml(self):
        """Fallback: Load agent ARN from .bedrock_agentcore.yaml (for backward compatibility)"""
        try:
            import yaml
            # Look for the config file in the chatbot directory (relative to code/ui/)
            config_path = "../services/chatbot/.bedrock_agentcore.yaml"
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    # Use default_agent to get the correct agent name
                    default_agent = config.get('default_agent')
                    if default_agent and default_agent in config.get('agents', {}):
                        agent_config = config['agents'][default_agent]
                        self.agent_arn = agent_config.get('bedrock_agentcore', {}).get('agent_arn')
                        self.memory_id = agent_config.get('memory', {}).get('memory_id')
                        
                        # Extract region from agent ARN or use current session region
                        self.region = self._parse_region_from_arn(self.agent_arn) if self.agent_arn else boto3.Session().region_name
                        if not self.region:
                            raise ValueError("No AWS region found. Please configure AWS CLI with default region.")
                        self.client = boto3.client('bedrock-agentcore', region_name=self.region)
                        print(f"Loaded agent ARN from YAML: {self.agent_arn}")
                    else:
                        print(f"Could not find default agent '{default_agent}' in YAML config")
            else:
                print(f"YAML config file not found at {config_path}")
        except Exception as e:
            print(f"Could not load agent ARN from YAML: {e}")
    
    def invoke_agent(self, question: str, session_id: str = None, actor_id: str = "ui_user") -> str:
        """Invoke AgentCore Runtime with question"""
        if not session_id:
            session_id = str(uuid.uuid4())
        
        if not self.agent_arn or not self.client:
            return "<p>❌ AgentCore not configured. Please deploy AgentCore first or check SSM parameter configuration.</p>"
        
        try:
            # Prepare request payload matching test-chatbot.sh
            request_payload = {
                "prompt": question,
                "user_id": actor_id,
                "session_id": session_id
            }
            
            # Invoke AgentCore using the correct API
            response = self.client.invoke_agent_runtime(
                agentRuntimeArn=self.agent_arn,
                qualifier="DEFAULT",
                payload=json.dumps(request_payload)
            )
            
            # Handle response (matching test-chatbot.sh logic)
            if "text/event-stream" in response.get("contentType", ""):
                # Handle streaming response
                content = []
                for line in response["response"].iter_lines(chunk_size=1):
                    if line:
                        line = line.decode("utf-8")
                        if line.startswith("data: "):
                            line = line[6:]
                            content.append(line)
                bot_response = "\n".join(content)
            else:
                # Handle non-streaming response
                try:
                    response_body = response["response"].read().decode("utf-8")
                    
                    if response_body.strip():
                        response_data = json.loads(response_body)
                        # Extract just the text content from the result
                        if isinstance(response_data, dict) and 'result' in response_data:
                            bot_response = response_data['result']
                        else:
                            bot_response = str(response_data)
                    else:
                        bot_response = "Empty response received"
                        
                except Exception as e:
                    bot_response = f"Error reading response: {e}"
            
            return bot_response
            
        except Exception as e:
            return f"<p>❌ Error: {str(e)}</p><p>Check CloudWatch logs: /aws/bedrock-agentcore/runtimes/confluence_chatbot_tutorial-*</p>"

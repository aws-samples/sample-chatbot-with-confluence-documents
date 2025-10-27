#!/usr/bin/env python3
"""
AgentCore deployment script for confluence chatbot
Supports both Terraform external data source mode and direct execution
"""

from bedrock_agentcore_starter_toolkit import Runtime
from boto3.session import Session
import boto3
import json
import os
import sys
import io
import contextlib
import time
import hashlib
import yaml

def clean_agentcore_cache(agent_name, external_mode=False):
    """Clean up stale AgentCore configurations by removing the cache file entirely"""
    try:
        # The YAML file is in the services/chatbot directory
        yaml_path = "services/chatbot/.bedrock_agentcore.yaml"
        if os.path.exists(yaml_path):
            log_message("Removing stale AgentCore cache file for fresh deployment...", external_mode)
            os.remove(yaml_path)
            log_message("✅ AgentCore cache file removed successfully", external_mode)
        else:
            log_message("No AgentCore cache file found, proceeding with fresh deployment", external_mode)
        
    except Exception as e:
        log_message(f"Warning: Could not remove AgentCore cache: {e}", external_mode)

@contextlib.contextmanager
def capture_agentcore_output(external_mode=False):
    """Capture AgentCore toolkit output to prevent interference with JSON output in external mode"""
    if external_mode:
        # In external mode, redirect stdout to stderr to keep JSON output clean
        old_stdout = sys.stdout
        sys.stdout = sys.stderr
        try:
            yield
        finally:
            sys.stdout = old_stdout
    else:
        # In non-external mode, let output go to stdout normally
        yield

def get_input_config():
    """Get configuration from either Terraform external data source (stdin) or environment variables"""
    try:
        # Try to read from stdin (Terraform external data source mode)
        if not sys.stdin.isatty():
            input_data = json.loads(sys.stdin.read())
            return {
                'ssm_parameter': input_data.get('ssm_parameter'),
                'execution_role': input_data.get('execution_role'),
                'external_mode': True
            }
    except (json.JSONDecodeError, EOFError):
        pass
    
    # Fall back to environment variables (backward compatibility)
    return {
        'ssm_parameter': os.environ.get('SSM_PARAMETER_NAME', '/confluence-bedrock/dev/config'),
        'execution_role': os.environ.get('EXECUTION_ROLE_ARN'),
        'external_mode': False
    }

def log_message(message, external_mode=False):
    """Log message to stderr in external mode, stdout otherwise."""
    if external_mode:
        # In external mode, only write to stderr to avoid interfering with JSON output
        print(message, file=sys.stderr, flush=True)
    else:
        print(message, flush=True)

def get_project_hash():
    """Generate a unique hash for this project to avoid naming conflicts"""
    # Use current working directory path to create unique identifier
    project_path = os.getcwd()
    return hashlib.md5(project_path.encode(), usedforsecurity=False).hexdigest()[:8]

def find_existing_resources(client, project_hash, external_mode=False):
    """Find existing AgentCore runtime for this project"""
    runtime_name_pattern = f"confluence_chatbot_tutorial_{project_hash}"
    
    existing_runtime = None
    
    try:
        # Check for existing runtime
        log_message(f"Checking for existing runtime with pattern: {runtime_name_pattern}", external_mode)
        runtimes_response = client.list_agent_runtimes()
        for runtime in runtimes_response.get('agentRuntimes', []):
            if runtime['agentRuntimeName'] == runtime_name_pattern:
                existing_runtime = runtime
                log_message(f"Found existing runtime: {runtime['agentRuntimeId']}", external_mode)
                break
    except Exception as e:
        log_message(f"Warning: Could not list runtimes: {e}", external_mode)
    
    return existing_runtime

def update_ssm_with_agentcore_info(ssm_client, ssm_parameter_name, memory_id, agent_name, agent_arn=None, memory_arn=None, external_mode=False):
    """Update SSM parameter with AgentCore runtime and memory information"""
    try:
        # Get existing config and parameter metadata
        response = ssm_client.get_parameter(Name=ssm_parameter_name, WithDecryption=True)
        config = json.loads(response['Parameter']['Value'])
        
        # Get parameter metadata to retrieve KMS key ID
        param_info = ssm_client.describe_parameters(
            Filters=[{'Key': 'Name', 'Values': [ssm_parameter_name]}]
        )
        
        # Update with AgentCore info
        config['memory_id'] = memory_id
        config['agent_name'] = agent_name
        if agent_arn:
            config['agent_arn'] = agent_arn
        if memory_arn:
            config['memory_arn'] = memory_arn
        
        # Prepare put_parameter arguments
        put_params = {
            'Name': ssm_parameter_name,
            'Value': json.dumps(config),
            'Type': 'SecureString',
            'Overwrite': True
        }
        
        # Add KMS key ID if parameter uses one
        if param_info['Parameters'] and 'KeyId' in param_info['Parameters'][0]:
            put_params['KeyId'] = param_info['Parameters'][0]['KeyId']
        
        # Update SSM parameter
        ssm_client.put_parameter(**put_params)
        log_message(f"Updated SSM parameter with AgentCore info: memory_id={memory_id}, agent_name={agent_name}, agent_arn={agent_arn}", external_mode)
    except Exception as e:
        log_message(f"Warning: Could not update SSM parameter with AgentCore info: {e}", external_mode)

# Get configuration
config = get_input_config()
ssm_parameter_name = config['ssm_parameter']
execution_role_arn = config['execution_role']
external_mode = config['external_mode']

# Get region from boto3 session
boto_session = Session()
region = boto_session.region_name

log_message(f"Using region: {region}", external_mode)
log_message(f"Using SSM parameter: {ssm_parameter_name}", external_mode)
log_message(f"Using execution role: {execution_role_arn}", external_mode)

# Generate project-specific identifiers
project_hash = get_project_hash()
log_message(f"Project hash: {project_hash}", external_mode)

# Create SSM client for parameter updates
ssm_client = boto3.client('ssm', region_name=region)

# Create bedrock-agentcore-control client for resource checking
client = boto3.client('bedrock-agentcore-control', region_name=region)

# Check for existing resources (Option 3: Force update instead of deletion)
existing_runtime = find_existing_resources(client, project_hash, external_mode)

# Handle AgentCore Runtime
agent_name = f"confluence_chatbot_tutorial_{project_hash}"

# OPTION 3: Force update existing runtime instead of deletion
if existing_runtime:
    log_message(f"Found existing runtime: {existing_runtime['agentRuntimeId']}, will force update with new code", external_mode)
else:
    log_message("No existing runtime found, will create new one", external_mode)

# OLD DELETION LOGIC (commented for rollback):
# if existing_runtime:
#     log_message(f"Found existing runtime: {existing_runtime['agentRuntimeId']}, destroying for fresh deployment", external_mode)
#     # Get memory ID before destroying runtime
#     runtime_details = client.get_agent_runtime(agentRuntimeId=existing_runtime['agentRuntimeId'])
#     memory_id = runtime_details.get('environmentVariables', {}).get('BEDROCK_AGENTCORE_MEMORY_ID')
#     # Destroy existing runtime (memory is auto-destroyed with runtime)
#     try:
#         log_message("Destroying existing AgentCore runtime...", external_mode)
#         client.delete_agent_runtime(agentRuntimeId=existing_runtime['agentRuntimeId'])
#         # ... rest of deletion logic
#     except Exception as e:
#         log_message(f"Warning: Could not destroy existing runtime: {e}", external_mode)

# Initialize Runtime (will update existing or create new)
# Clean up stale AgentCore cache first
clean_agentcore_cache(agent_name, external_mode)

# Capture AgentCore toolkit output to prevent JSON interference
with capture_agentcore_output(external_mode):
    agentcore_runtime = Runtime()

# Change to services/chatbot directory for correct entrypoint resolution (if not already there)
original_cwd = os.getcwd()
if not original_cwd.endswith("services/chatbot"):
    os.chdir("services/chatbot")
    changed_dir = True
else:
    changed_dir = False

# Configure with deployment parameters
log_message(f"Configuring AgentCore Runtime: {agent_name}", external_mode)

with capture_agentcore_output(external_mode):
    response = agentcore_runtime.configure(
        entrypoint="agent.py",
        auto_create_execution_role=False,
        execution_role=execution_role_arn,
        auto_create_ecr=True,
        requirements_file="requirements.txt",
        region=region,
        agent_name=agent_name
    )

# Change back to original directory (if we changed it)
if changed_dir:
    os.chdir(original_cwd)

log_message("Configuration response: " + str(response), external_mode)

# Launch with auto-update and environment variables
log_message("Launching AgentCore Runtime...", external_mode)

# Capture AgentCore toolkit output to prevent JSON interference
with capture_agentcore_output(external_mode):
    launch_result = agentcore_runtime.launch(
        auto_update_on_conflict=True,
        env_vars={
            "SSM_PARAMETER_NAME": ssm_parameter_name
        }
    )
log_message("Launch result: " + str(launch_result), external_mode)

# Wait for deployment to complete
log_message("Waiting for deployment to complete...", external_mode)
status_response = agentcore_runtime.status()
status = status_response.endpoint['status']
end_status = ['READY', 'CREATE_FAILED', 'DELETE_FAILED', 'UPDATE_FAILED']

# Poll interval for AgentCore status updates (intentional wait for async deployment)
def get_polling_interval():
    return 10

while status not in end_status:
    log_message(f"Status: {status}", external_mode)
    time.sleep(get_polling_interval())  # Intentional: Wait for AgentCore async status update
    status_response = agentcore_runtime.status()
    status = status_response.endpoint['status']

log_message(f"Final status: {status}", external_mode)

if status == 'READY':
    log_message("✅ AgentCore Runtime deployed successfully!", external_mode)
    log_message(f"Agent ARN: {launch_result.agent_arn}", external_mode)
    log_message(f"Environment variables: SSM_PARAMETER_NAME={ssm_parameter_name}", external_mode)
    
    # Get runtime details to extract auto-created memory ID
    runtime_id = launch_result.agent_arn.split('/')[-1]
    runtime_details = client.get_agent_runtime(agentRuntimeId=runtime_id)
    memory_id = runtime_details.get('environmentVariables', {}).get('BEDROCK_AGENTCORE_MEMORY_ID')
    
    if not memory_id:
        log_message("ERROR: Runtime created but no memory ID found in environment variables", external_mode)
        log_message("This may indicate a change in AgentCore behavior. Please check AWS documentation.", external_mode)
        sys.exit(1)
    
    log_message(f"Using runtime's auto-created memory: {memory_id}", external_mode)
    
    # Extract account ID from agent ARN for memory ARN construction
    account_id = launch_result.agent_arn.split(':')[4] if ':' in launch_result.agent_arn else None
    memory_arn = f"arn:aws:bedrock-agentcore:{region}:{account_id}:memory/{memory_id}" if memory_id and account_id else None
    
    # Update SSM with final runtime info
    update_ssm_with_agentcore_info(ssm_client, ssm_parameter_name, memory_id, agent_name, launch_result.agent_arn, memory_arn, external_mode)
    
    # Output JSON for Terraform external data source
    if external_mode:
        result = {
            "runtime_arn": launch_result.agent_arn,
            "memory_id": memory_id,
            "agent_name": agent_name
        }
        print(json.dumps(result))
    
    sys.exit(0)
else:
    log_message(f"❌ Deployment failed with status: {status}", external_mode)
    sys.exit(1)

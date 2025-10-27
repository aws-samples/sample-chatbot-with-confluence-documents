#!/usr/bin/env python3
"""
AgentCore cleanup script for confluence chatbot
Handles destruction of AgentCore Runtime and Memory resources using proper AWS APIs
Enhanced with robust error handling and comprehensive cleanup
"""

import boto3
from botocore.exceptions import ClientError
import sys
import time
import json
import os

def extract_runtime_id_from_arn(runtime_arn):
    """Extract runtime ID from ARN format: arn:aws:bedrock-agentcore:region:account:agent-runtime/runtime-id"""
    return runtime_arn.split('/')[-1]

def clean_ssm_parameter(ssm_client, ssm_parameter_name, runtime_arn=None, memory_id=None):
    """Clean AgentCore references from SSM parameter"""
    try:
        print("🔄 Cleaning SSM parameter references...")
        
        # Get current SSM parameter
        response = ssm_client.get_parameter(Name=ssm_parameter_name, WithDecryption=True)
        config_data = json.loads(response['Parameter']['Value'])
        
        # Get parameter metadata to retrieve KMS key ID
        param_info = ssm_client.describe_parameters(
            Filters=[{'Key': 'Name', 'Values': [ssm_parameter_name]}]
        )
        
        # Remove AgentCore references
        cleaned = False
        if runtime_arn and 'agent_arn' in config_data:
            if runtime_arn == config_data['agent_arn']:
                config_data.pop('agent_arn', None)
                config_data.pop('agent_name', None)
                cleaned = True
                print("  ✅ Removed agent references from SSM parameter")
        
        if memory_id and 'memory_id' in config_data:
            if memory_id == config_data['memory_id']:
                config_data.pop('memory_id', None)
                config_data.pop('memory_arn', None)
                cleaned = True
                print("  ✅ Removed memory references from SSM parameter")
        
        # Update SSM parameter if changes were made
        if cleaned:
            # Prepare put_parameter arguments
            put_params = {
                'Name': ssm_parameter_name,
                'Value': json.dumps(config_data),
                'Type': 'SecureString',
                'Overwrite': True
            }
            
            # Add KMS key ID if parameter uses one
            if param_info['Parameters'] and 'KeyId' in param_info['Parameters'][0]:
                put_params['KeyId'] = param_info['Parameters'][0]['KeyId']
            
            ssm_client.put_parameter(**put_params)
            print("  ✅ SSM parameter updated successfully")
        else:
            print("  ℹ️  No SSM parameter cleanup needed")
            
    except Exception as e:
        print(f"  ⚠️  Warning: Could not clean SSM parameter: {e}")

def clean_local_config(runtime_id=None, memory_id=None, agent_name=None):
    """Delete local .bedrock_agentcore.yaml file"""
    config_file = ".bedrock_agentcore.yaml"
    if not os.path.exists(config_file):
        print("  ℹ️  No local config file to delete")
        return
        
    try:
        print("🔄 Deleting local configuration file...")
        os.remove(config_file)
        print("  ✅ Local config file deleted successfully")
    except Exception as e:
        print(f"  ⚠️  Warning: Could not delete local config: {e}")

def safe_delete_runtime_endpoints(client, runtime_id):
    """Delete all non-DEFAULT runtime endpoints before deleting the runtime"""
    try:
        print("🔄 Checking for runtime endpoints to delete...")
        
        # List all endpoints for this runtime
        response = client.list_agent_runtime_endpoints(agentRuntimeId=runtime_id)
        endpoints = response.get('runtimeEndpoints', [])
        
        if not endpoints:
            print("  ℹ️  No runtime endpoints found")
            return True
        
        # Filter out DEFAULT endpoint (auto-deleted with runtime)
        non_default_endpoints = [ep for ep in endpoints if ep.get('name') != 'DEFAULT']
        
        if not non_default_endpoints:
            print("  ℹ️  Only DEFAULT endpoint found (will be auto-deleted with runtime)")
            return True
        
        print(f"  Found {len(non_default_endpoints)} non-DEFAULT endpoint(s) to delete")
        
        # Delete each non-DEFAULT endpoint
        success = True
        for endpoint in non_default_endpoints:
            endpoint_name = endpoint.get('name')
            try:
                print(f"  🔄 Deleting endpoint: {endpoint_name}")
                delete_response = client.delete_agent_runtime_endpoint(
                    agentRuntimeId=runtime_id,
                    endpointName=endpoint_name
                )
                print(f"    ✅ Endpoint deletion initiated with status: {delete_response.get('status', 'Unknown')}")
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    print(f"    ℹ️  Endpoint {endpoint_name} already deleted")
                else:
                    print(f"    ⚠️  Warning: Could not delete endpoint {endpoint_name}: {e}")
                    success = False
            except Exception as e:
                print(f"    ⚠️  Warning: Could not delete endpoint {endpoint_name}: {e}")
                success = False
        
        return success
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            print("  ℹ️  Runtime not found, no endpoints to delete")
            return True
        else:
            print(f"  ⚠️  Warning: Could not list runtime endpoints: {e}")
            return False
    except Exception as e:
        print(f"  ⚠️  Warning: Could not list runtime endpoints: {e}")
        return False

def safe_delete_runtime(client, runtime_id):
    """Safely delete AgentCore Runtime with proper error handling
    
    Note: Runtime deletion automatically cleans up its associated memory.
    No need to explicitly delete memory separately.
    """
    try:
        print("🔄 Deleting AgentCore Runtime (will auto-cleanup associated memory)...")
        
        # First check if runtime exists
        try:
            client.get_agent_runtime(agentRuntimeId=runtime_id)
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                print("ℹ️  AgentCore Runtime already deleted or not found")
                return True
            raise e
        
        # Delete the runtime
        delete_response = client.delete_agent_runtime(agentRuntimeId=runtime_id)
        print(f"  Runtime deletion initiated with status: {delete_response.get('status', 'Unknown')}")
        
        # Wait for deletion to complete
        print("  ⏳ Waiting for runtime deletion...")
        max_wait = 300  # 5 minutes
        wait_time = 0
        # Poll interval for AgentCore deletion status (intentional wait for async deletion)
        def get_polling_interval():
            return 10
        
        while wait_time < max_wait:
            try:
                runtime_response = client.get_agent_runtime(agentRuntimeId=runtime_id)
                status = runtime_response.get('status', 'Unknown')
                
                if status == 'DELETING':
                    print(f"    Status: {status}")
                    time.sleep(get_polling_interval())  # Intentional: Wait for AgentCore async deletion
                    wait_time += get_polling_interval()
                else:
                    print(f"    Unexpected status during deletion: {status}")
                    break
                    
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    print("  ✅ AgentCore Runtime deleted successfully (memory auto-cleaned)")
                    return True
                else:
                    print(f"  ⚠️  Error checking runtime status: {e}")
                    break
            except Exception as e:
                print(f"  ⚠️  Error checking runtime status: {e}")
                break
        
        if wait_time >= max_wait:
            print("  ⚠️  Timeout waiting for runtime deletion, but continuing...")
            return False
        
        return True
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            print("ℹ️  AgentCore Runtime already deleted or not found")
            return True
        else:
            print(f"⚠️  Warning: Could not delete AgentCore Runtime: {e}")
            return False
    except Exception as e:
        print(f"⚠️  Warning: Could not delete AgentCore Runtime: {e}")
        return False

def safe_delete_memory(client, memory_id):
    """Safely delete AgentCore Memory with proper error handling"""
    try:
        print("🔄 Deleting AgentCore Memory...")
        
        # First check if memory exists
        try:
            client.get_memory(memoryId=memory_id)
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                print("ℹ️  AgentCore Memory already deleted or not found")
                return True
            raise e
        
        delete_response = client.delete_memory(memoryId=memory_id)
        print(f"  Memory deletion initiated with status: {delete_response.get('status', 'Unknown')}")
        print("  ✅ AgentCore Memory deletion initiated successfully")
        return True
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            print("ℹ️  AgentCore Memory already deleted or not found")
            return True
        else:
            print(f"⚠️  Warning: Could not delete AgentCore Memory: {e}")
            return False
    except Exception as e:
        print(f"⚠️  Warning: Could not delete AgentCore Memory: {e}")
        return False

def main():
    # Get SSM parameter name from environment or command line
    ssm_parameter_name = os.environ.get('SSM_PARAMETER_NAME')
    if not ssm_parameter_name and len(sys.argv) > 1:
        ssm_parameter_name = sys.argv[1]
    
    if not ssm_parameter_name:
        print("ERROR: SSM_PARAMETER_NAME environment variable or command line argument required", file=sys.stderr)
        sys.exit(1)
    
    # Get region from boto3 session
    session = boto3.Session()
    region = session.region_name
    
    if not region:
        print("ERROR: AWS region not configured. Please set AWS_DEFAULT_REGION or configure AWS CLI.", file=sys.stderr)
        sys.exit(1)
    
    print(f"🌍 Using AWS region: {region}")
    
    # Initialize clients
    client = boto3.client('bedrock-agentcore-control', region_name=region)
    ssm_client = boto3.client('ssm', region_name=region)
    
    # Read runtime info from SSM parameter
    runtime_arn = None
    memory_id = None
    agent_name = None
    
    try:
        print(f"📖 Reading AgentCore info from SSM parameter: {ssm_parameter_name}")
        response = ssm_client.get_parameter(Name=ssm_parameter_name, WithDecryption=True)
        config_data = json.loads(response['Parameter']['Value'])
        
        runtime_arn = config_data.get('agent_arn')
        memory_id = config_data.get('memory_id')
        agent_name = config_data.get('agent_name')
        
        if not runtime_arn and not memory_id:
            print("ℹ️  No AgentCore resources found in SSM parameter - nothing to destroy")
            sys.exit(0)
            
        print(f"  Found runtime ARN: {runtime_arn}")
        print(f"  Found memory ID: {memory_id}")
        print(f"  Found agent name: {agent_name}")
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'ParameterNotFound':
            print("ℹ️  SSM parameter not found - nothing to destroy")
            sys.exit(0)
        else:
            print(f"⚠️  Warning: Could not read SSM parameter: {e}")
    
    print(f"🗑️  Starting AgentCore cleanup in region: {region}")
    print(f"Runtime ARN: {runtime_arn}")
    print(f"Memory ID: {memory_id}")
    print(f"Agent Name: {agent_name}")
    print(f"SSM Parameter: {ssm_parameter_name}")
    
    success = True
    
    # Extract runtime ID from ARN if provided
    runtime_id = None
    if runtime_arn:
        runtime_id = extract_runtime_id_from_arn(runtime_arn)
        print(f"Runtime ID: {runtime_id}")
    
    # 1. Delete runtime endpoints (except DEFAULT which is auto-deleted)
    if runtime_id:
        if not safe_delete_runtime_endpoints(client, runtime_id):
            success = False
    
    # 2. Delete AgentCore Runtime
    if runtime_id:
        if not safe_delete_runtime(client, runtime_id):
            success = False
    else:
        print("ℹ️  No runtime ARN provided, skipping runtime deletion")
    
    # 3. Delete AgentCore Memory separately (not automatically deleted with runtime)
    if memory_id:
        if not safe_delete_memory(client, memory_id):
            success = False
    else:
        print("ℹ️  No memory ID provided, skipping memory deletion")
    
    # 4. Clean up configuration references
    if ssm_parameter_name:
        clean_ssm_parameter(ssm_client, ssm_parameter_name, runtime_arn, memory_id)
    
    clean_local_config(runtime_id, memory_id, agent_name)
    
    if success:
        print("🎉 AgentCore cleanup completed successfully!")
        sys.exit(0)
    else:
        print("❌ AgentCore cleanup completed with warnings")
        sys.exit(1)

if __name__ == "__main__":
    main()

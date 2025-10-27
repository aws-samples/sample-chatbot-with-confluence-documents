# Confluence to Bedrock KB Integration with AgentCore Chatbot

## Overview
Syncs Confluence articles to Bedrock KB with image support, incremental sync, Terraform deployment, and AgentCore-powered chatbot with LangGraph for intelligent retrieval via Claude Sonnet 3.7.

## Architecture
1. **Ingestion**: Lambda fetches Confluence → processes images → S3 → Bedrock KB (SSM state tracking)
2. **Chatbot**: AgentCore Runtime with LangGraph agent → Memory management → Semantic search → HTML response
3. **Infrastructure**: Terraform modules (shared, ingestion, chatbot with AgentCore)

## Usage
1. `./code/scripts/setup.sh` - install dependencies and create venv
2. `./code/scripts/deploy-all.sh` - full deployment with configuration setup
3. `./code/scripts/upload-token.sh` - store Confluence token
4. `./code/scripts/configure-spaces.sh` - configure Confluence spaces and settings
5. `./code/scripts/toggle-pipeline.sh enable` - start ingestion
6. `./code/scripts/run-chatbot-local-ui.sh` - launch Streamlit web UI for testing

### Modular Deployment
- `./code/scripts/deploy-all.sh` - Deploy all modules (shared + ingestion + chatbot)
- `./code/scripts/deploy-ingestion.sh` - Deploy ingestion module only
- `./code/scripts/deploy-chatbot.sh` - Deploy chatbot module only

## Files

### Terraform (`./code/`)
- `main.tf` - provider config (AWS, archive, external), calls modules. **UPDATED**: Now passes knowledge_base_top_n and llm_model_id to shared module
- `variables.tf` - input vars (Confluence, AWS, KB settings). **UPDATED**: Added knowledge_base_top_n and llm_model_id variables
- `outputs.tf` - exports (S3 bucket, Lambda names, EventBridge rule, AgentCore execution role ARN, SSM parameter ARN)
- `terraform.tfvars.example` - config template. **UPDATED**: Added new configuration parameters with examples

### Modules (`./code/modules/`)
- `shared/` - S3 bucket, Secrets Manager, SSM parameter (includes s3_bucket_name, ssm_parameter_arn output)
- `ingestion/` - Lambda, SSM crawl state, EventBridge, IAM (outputs ssm_parameter_name)
- `chatbot/` - AgentCore Runtime with custom IAM execution role, external data source deployment, destroy provisioner

### Services (`./code/services/`)
- `ingestion/handler.py` - Lambda entry for Confluence sync. Imports: json,logging,os,boto3,datetime,typing. Classes: SSMCrawlTracker(SSM state mgmt), SimpleConfig. Methods: get/save_last_crawl_time, load_configuration, process_space_incrementally, lambda_handler. **UPDATED**: Removed hardcoded us-east-1 region fallback, now uses boto3 session region with proper error handling. **UPDATED**: Fixed _save_crawl_state to use SecureString with KMS key retrieval to maintain encryption consistency
- `chatbot/agent.py` - AgentCore chatbot with LangGraph. Imports: json,os,boto3,botocore.config,re,bleach,typing,langchain_core,langgraph,bedrock_agentcore,bedrock_agentcore.memory,langchain_aws. Classes: ChatbotState(TypedDict with messages and kb_results), ChatbotAgent. Methods: _load_config, _build_graph, _generate_search_query, _search_knowledge_base, _generate_response, _format_html, _markdown_to_html, sanitize_html, invoke, agent_invocation. Uses LangGraph state for thread-safe KB results storage. S3 client configured with Signature Version 4 for KMS-encrypted object presigned URLs. **UPDATED**: Added HTML sanitization with bleach library to prevent XSS attacks from malicious Confluence content. sanitize_html() whitelists safe HTML tags and strips all script tags and event handlers before rendering. **UPDATED**: Configured S3 client with signature_version='s3v4' to support presigned URLs for KMS-encrypted objects
- `chatbot/deploy_agent.py` - AgentCore deployment script. Imports: boto3,time,bedrock_agentcore_starter_toolkit.Runtime,boto3.session.Session. Methods: get_input_config (JSON/env input), log_message (external mode logging - FIXED to only write to stderr in external mode), get_project_hash, find_existing_resources (checks for existing runtime only), update_ssm_with_agentcore_info (stores agent_arn, agent_name, memory_id, memory_arn in SSM - uses WithDecryption=True for SSM parameter retrieval and SecureString with KMS key for updates), configure (with custom execution role), launch, status polling. After runtime is READY, queries get_agent_runtime() to extract auto-created memory_id from environmentVariables['BEDROCK_AGENTCORE_MEMORY_ID'] and stores in SSM. Supports Terraform external data source mode with JSON input/output. No longer creates memory explicitly - relies on runtime's auto-created memory. **UPDATED**: Fixed log_message function to only write to stderr in external mode, preventing JSON parsing errors in Terraform external data source. **UPDATED**: Fixed update_ssm_with_agentcore_info to use WithDecryption=True when retrieving SSM parameter and SecureString with KMS key when updating to maintain encryption consistency
- `chatbot/destroy_agent.py` - AgentCore cleanup script. Imports: boto3,bedrock_agentcore_starter_toolkit.Runtime. Methods: main (CLI args handling), runtime termination, clean_ssm_parameter (removes AgentCore references from SSM). Handles idempotent cleanup for terraform destroy. Runtime deletion automatically cleans up associated memory - no explicit memory deletion needed. **UPDATED**: Fixed SSM parameter updates to use SecureString with KMS key retrieval to maintain encryption consistency
- `chatbot/test_lifecycle.py` - Test script for AgentCore lifecycle management validation
- `chatbot/requirements.txt` - AgentCore and LangGraph dependencies. **UPDATED**: Added bleach>=6.0.0 for HTML sanitization
- `ingestion/confluence_bedrock/` - core library copy:
  - `models/confluence_models.py` - Confluence data structures. Imports: dataclasses,typing,datetime. Classes: PageVersion,ConfluencePage,ConfluenceSpace
  - `models/bedrock_models.py` - Bedrock data structures. Imports: dataclasses,typing,datetime. Classes: BedrockMetadata,BedrockDocument,IngestResponse
  - `models/config_models.py` - Config dataclass. Imports: json,os,dataclasses,typing. Classes: Config(all settings)
  - `services/confluence_service.py` - Confluence API client. Imports: json,logging,typing,datetime,urllib.*,base64,models. Classes: ConfluenceService(API calls)
  - `services/bedrock_service.py` - Bedrock KB client. Imports: boto3,typing,logging,datetime,models. Classes: BedrockService(KB operations)
  - `services/s3_service.py` - S3 operations. Imports: boto3,logging,typing,urllib.parse,os,botocore,models. Classes: S3Service(upload/download)
  - `services/crawler_service.py` - Main orchestrator. Imports: os,datetime,typing,logging,models,utils,services. Classes: CrawlerService(sync workflow)
  - `utils/content_processor.py` - Content transformation. Imports: re,typing,logging,models. Classes: ContentProcessor(text processing)
  - `utils/html_converter.py` - HTML output formatting. Imports: re,os,typing,datetime,logging. Classes: HTMLConverter(markdown to HTML)
  - `utils/image_processor.py` - Image handling. Imports: os,logging,typing,urllib.*,base64,models,services. Classes: ImageProcessor(download/upload images)

### UI (`./code/ui/`)
- `app.py` - Streamlit web interface for chatbot testing. Imports: streamlit,uuid,agentcore_client. Features: chat interface, session management, AgentCore integration
- `agentcore_client.py` - AgentCore client wrapper. Imports: boto3,json,uuid,os,re. Classes: AgentCoreClient. Methods: invoke_agent, _load_agentcore_config (reads from SSM parameter via AGENTCORE_SSM_PARAMETER_ARN env var), _parse_region_from_arn, _load_agent_arn_from_yaml (fallback). Supports SSM parameter ARN parsing and YAML fallback for backward compatibility. **UPDATED**: Removed hardcoded us-west-2 region fallbacks, now uses boto3 session region with proper error handling

### Scripts (`./code/scripts/`)
- `setup.sh` - install Terraform, create venv, deps. **UPDATED**: Now uses shared utility functions from common.sh
- `setup-for-dev.sh` - **NEW**: Development environment setup. Runs setup.sh first, then checks for Finch or Docker container runtime (required for ASH security scanning) and fails with helpful message if neither is found. Installs development dependencies from requirements-dev.txt including ASH for security scanning
- `common.sh` - **NEW**: shared utility functions for all deployment scripts including activate_venv(), prompt_input(), prompt_yes_no(), check_aws_cli(), collect_confluence_spaces(), create_full_terraform_tfvars(), create_minimal_terraform_tfvars(), terraform_init_and_plan(), terraform_apply_with_confirmation(), validate_terraform_tfvars(), show_config_preview(), detect_python(), prompt_secure_input(), find_and_change_to_code_directory()
- `deploy-all.sh` - interactive config, terraform plan/apply for all modules. **UPDATED**: Now uses shared utility functions from common.sh, standardized prompting and validation
- `deploy-ingestion.sh` - deploy ingestion module only. **UPDATED**: Now uses shared utility functions, removed code duplication
- `deploy-chatbot.sh` - deploy chatbot module only. **UPDATED**: Now uses shared utility functions, improved parameter validation and terraform.tfvars creation
- `destroy-chatbot.sh` - destroy chatbot module only. **UPDATED**: Now uses shared utility functions, standardized confirmation prompts
- `destroy-ingestion.sh` - destroy ingestion module only. **UPDATED**: Now uses shared utility functions, standardized confirmation prompts
- `destroy-all.sh` - destroy all infrastructure with strong confirmation. **UPDATED**: Now uses shared utility functions, standardized confirmation prompts
- `upload-token.sh` - securely upload Confluence API token to AWS Secrets Manager. **UPDATED**: Now uses shared utility functions, improved secure input handling
- `reconfigure-parameters.sh` - interactive reconfiguration of Confluence parameters and settings in SSM parameter. **UPDATED**: Now uses shared utility functions from common.sh, allows users to press Enter to keep current values, renamed from configure-spaces.sh
- `toggle-pipeline.sh` - enable/disable EventBridge rule. **UPDATED**: Now uses shared utility functions
- `reset-crawl-state.sh` - reset SSM crawl state. **UPDATED**: Now uses shared utility functions, improved prompting
- `run-chatbot-local-ui.sh` - launch Streamlit web UI for chatbot testing (localhost:8501). **UPDATED**: Now uses shared utility functions, improved SSM parameter ARN handling
- `test-chatbot.sh` - interactive AgentCore chatbot testing
- `scan-code.sh` - **NEW**: Run ASH (Automated Security Helper) security scan on Terraform and Python code. Uses container mode (Finch or Docker) to run comprehensive security checks including Checkov (IaC), Bandit (Python), detect-secrets, and other tools. Saves detailed report to ./dev/tmp/ash-security-report.txt. Non-blocking (always exits 0) to allow CI/CD integration

### Root
- `README.md` - full documentation
- `code/requirements.txt` - boto3>=1.34.0, botocore>=1.34.0, bedrock-agentcore>=0.1.5, bedrock-agentcore-starter-toolkit>=0.1.0, langgraph>=0.2.0, langchain-aws>=0.1.0, langchain-core>=0.3.0, streamlit>=1.28.0, PyYAML>=6.0
- `code/requirements-dev.txt` - **NEW**: Development dependencies including git+https://github.com/awslabs/automated-security-helper.git@v3.1.2 for security scanning
- `.gitignore` - excludes Python cache, Terraform state, secrets, AgentCore generated files

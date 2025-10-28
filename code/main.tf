terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
    external = {
      source  = "hashicorp/external"
      version = "~> 2.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# Data sources
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# Shared resources
module "shared" {
  source = "./modules/shared"
  
  project_name        = var.project_name
  environment         = var.environment
  confluence_base_url = var.confluence_base_url
  confluence_email    = var.confluence_email
  knowledge_base_id   = var.knowledge_base_id
  data_source_id      = var.data_source_id
  confluence_spaces   = var.confluence_spaces
  knowledge_base_top_n = var.knowledge_base_top_n
  llm_model_id        = var.llm_model_id
  aws_region          = var.aws_region
}

# Ingestion module
module "ingestion" {
  source = "./modules/ingestion"
  
  project_name           = var.project_name
  environment           = var.environment
  s3_bucket_name        = module.shared.s3_bucket_name
  secrets_manager_arn   = module.shared.secrets_manager_arn
  ssm_parameter_name    = module.shared.ssm_parameter_name
  lambda_timeout        = var.ingestion_lambda_timeout
  lambda_memory_size    = var.ingestion_lambda_memory_size
  knowledge_base_id     = var.knowledge_base_id
  kms_ssm_key_arn       = module.shared.kms_ssm_key_arn
  kms_secrets_key_arn   = module.shared.kms_secrets_key_arn
}

# Chatbot module
module "chatbot" {
  source = "./modules/chatbot"
  
  project_name           = var.project_name
  environment           = var.environment
  s3_bucket_name        = module.shared.s3_bucket_name
  ssm_parameter_name    = module.shared.ssm_parameter_name
  lambda_timeout        = var.chatbot_lambda_timeout
  lambda_memory_size    = var.chatbot_lambda_memory_size
  kms_ssm_key_arn       = module.shared.kms_ssm_key_arn
}

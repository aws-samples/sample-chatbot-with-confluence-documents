output "aws_region" {
  description = "AWS region where resources are deployed"
  value       = var.aws_region
}

output "s3_bucket_name" {
  description = "Name of the S3 bucket for storing images"
  value       = module.shared.s3_bucket_name
}

output "secrets_manager_arn" {
  description = "ARN of the Secrets Manager secret for Confluence API token"
  value       = module.shared.secrets_manager_arn
}

output "ssm_parameter_name" {
  description = "Name of the SSM parameter for configuration"
  value       = module.shared.ssm_parameter_name
}

output "ssm_parameter_arn" {
  description = "ARN of the SSM parameter for configuration"
  value       = module.shared.ssm_parameter_arn
}

output "kms_ssm_key_id" {
  description = "ID of the KMS key for SSM encryption"
  value       = module.shared.kms_ssm_key_arn
}

output "ingestion_lambda_function_name" {
  description = "Name of the ingestion Lambda function"
  value       = module.ingestion.lambda_function_name
}

output "eventbridge_rule_name" {
  description = "Name of the EventBridge rule for scheduling"
  value       = module.ingestion.eventbridge_rule_name
}

output "agentcore_execution_role_arn" {
  description = "ARN of the AgentCore execution role"
  value       = module.chatbot.agentcore_execution_role_arn
}

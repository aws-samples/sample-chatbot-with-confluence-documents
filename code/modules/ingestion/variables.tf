variable "project_name" {
  description = "Name of the project"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "s3_bucket_name" {
  description = "Name of the S3 bucket"
  type        = string
}

variable "secrets_manager_arn" {
  description = "ARN of the Secrets Manager secret"
  type        = string
}

variable "ssm_parameter_name" {
  description = "Name of the SSM parameter"
  type        = string
}

variable "lambda_timeout" {
  description = "Lambda function timeout in seconds"
  type        = number
  default     = 900
}

variable "lambda_memory_size" {
  description = "Lambda function memory size in MB"
  type        = number
  default     = 512
}

variable "knowledge_base_id" {
  description = "Bedrock Knowledge Base ID"
  type        = string
}

variable "kms_ssm_key_arn" {
  description = "ARN of the KMS key for SSM encryption"
  type        = string
}

variable "kms_secrets_key_arn" {
  description = "ARN of the KMS key for Secrets Manager encryption"
  type        = string
}

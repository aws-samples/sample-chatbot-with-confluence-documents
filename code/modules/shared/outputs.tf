output "s3_bucket_name" {
  description = "Name of the S3 bucket"
  value       = aws_s3_bucket.confluence_images.bucket
}

output "s3_bucket_arn" {
  description = "ARN of the S3 bucket"
  value       = aws_s3_bucket.confluence_images.arn
}

output "secrets_manager_arn" {
  description = "ARN of the Secrets Manager secret"
  value       = aws_secretsmanager_secret.confluence_token.arn
}

output "ssm_parameter_name" {
  description = "Name of the SSM parameter"
  value       = aws_ssm_parameter.config.name
}

output "kms_ssm_key_arn" {
  description = "ARN of the KMS key for SSM encryption"
  value       = aws_kms_key.ssm.arn
}

output "kms_secrets_key_arn" {
  description = "ARN of the KMS key for Secrets Manager encryption"
  value       = aws_kms_key.secrets.arn
}

output "ssm_parameter_arn" {
  description = "ARN of the SSM parameter"
  value       = aws_ssm_parameter.config.arn
}

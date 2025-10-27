output "lambda_function_name" {
  description = "Name of the ingestion Lambda function"
  value       = aws_lambda_function.ingestion.function_name
}

output "lambda_function_arn" {
  description = "ARN of the ingestion Lambda function"
  value       = aws_lambda_function.ingestion.arn
}

output "eventbridge_rule_name" {
  description = "Name of the EventBridge rule"
  value       = aws_cloudwatch_event_rule.ingestion_schedule.name
}

output "ssm_parameter_name" {
  description = "Name of the SSM parameter containing configuration"
  value       = var.ssm_parameter_name
}

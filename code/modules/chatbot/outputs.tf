output "agentcore_execution_role_arn" {
  description = "ARN of the AgentCore execution role"
  value       = aws_iam_role.agentcore_execution.arn
}

# Note: AgentCore runtime details are stored in SSM parameter after deployment
# These outputs will be empty until after first apply completes
output "agentcore_deployment_note" {
  description = "Note about AgentCore deployment"
  value       = "AgentCore runtime details are stored in SSM parameter: ${var.ssm_parameter_name}. Run 'terraform refresh' after deployment to see values."
}

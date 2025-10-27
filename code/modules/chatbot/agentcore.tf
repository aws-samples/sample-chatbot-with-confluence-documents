# AgentCore Runtime for Chatbot

# IAM role for AgentCore Runtime
resource "aws_iam_role" "agentcore_execution" {
  name = "${var.project_name}-${var.environment}-agentcore-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "bedrock-agentcore.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "agentcore_execution" {
  name = "${var.project_name}-${var.environment}-agentcore-execution-policy"
  role = aws_iam_role.agentcore_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid = "ECRImageAccess"
        Effect = "Allow"
        Action = [
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer"
        ]
        Resource = [
          "arn:aws:ecr:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:repository/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "logs:DescribeLogStreams",
          "logs:CreateLogGroup"
        ]
        Resource = [
          "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "logs:DescribeLogGroups"
        ]
        Resource = [
          "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = [
          "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"
        ]
      },
      {
        # Justification: ecr:GetAuthorizationToken requires wildcard resource per AWS service limitation
        # This permission is necessary for AgentCore to pull container images from ECR
        # AWS does not support resource-level permissions for GetAuthorizationToken
        # Scope: Limited to ECR authentication only, no data access
        Sid = "ECRTokenAccess"
        Effect = "Allow"
        # nosemgrep: terraform.lang.security.iam.no-iam-creds-exposure
        Action = [
          "ecr:GetAuthorizationToken"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "xray:PutTraceSegments",
          "xray:PutTelemetryRecords",
          "xray:GetSamplingRules",
          "xray:GetSamplingTargets"
        ]
        Resource = ["*"]
      },
      {
        Effect = "Allow"
        Resource = "*"
        Action = "cloudwatch:PutMetricData"
        Condition = {
          StringEquals = {
            "cloudwatch:namespace" = "bedrock-agentcore"
          }
        }
      },
      {
        Sid = "GetAgentAccessToken"
        Effect = "Allow"
        Action = [
          "bedrock-agentcore:GetWorkloadAccessToken",
          "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
          "bedrock-agentcore:GetWorkloadAccessTokenForUserId"
        ]
        Resource = [
          "arn:aws:bedrock-agentcore:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:workload-identity-directory/default",
          "arn:aws:bedrock-agentcore:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:workload-identity-directory/default/workload-identity/agentName-*"
        ]
      },
      {
        Sid = "BedrockModelInvocation"
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = [
          "arn:aws:bedrock:*::foundation-model/*",
          "arn:aws:bedrock:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "bedrock:Retrieve"
        ]
        Resource = [
          "arn:aws:bedrock:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:PutParameter"
        ]
        Resource = [
          "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter${var.ssm_parameter_name}",
          "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter/agentcore/*"
        ]
      },
      {
        # Justification: Resource is constrained to specific S3 bucket via variable interpolation
        # This permission is necessary for chatbot to generate presigned URLs for images
        # Scope: Read-only access limited to single bucket containing Confluence images
        # Security: Bucket name is dynamically scoped, no wildcard bucket access
        Effect = "Allow"
        # nosemgrep: terraform.lang.security.iam.no-iam-data-exfiltration
        Action = [
          "s3:GetObject"
        ]
        Resource = "arn:aws:s3:::${var.s3_bucket_name}/*"
      },
      {
        Sid = "AgentCoreMemoryAccess"
        Effect = "Allow"
        Action = [
          "bedrock-agentcore:ListEvents",
          "bedrock-agentcore:GetEvent",
          "bedrock-agentcore:CreateEvent",
          "bedrock-agentcore:UpdateEvent",
          "bedrock-agentcore:DeleteEvent",
          "bedrock-agentcore:GetLastKTurns",
          "bedrock-agentcore:SearchMemories"
        ]
        Resource = [
          "arn:aws:bedrock-agentcore:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:memory/*"
        ]
      },
      {
        Sid = "KMSDecryptAccess"
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey",
          "kms:DescribeKey"
        ]
        Resource = [
          var.kms_ssm_key_arn
        ]
        Condition = {
          StringEquals = {
            "kms:ViaService" = [
              "ssm.${data.aws_region.current.name}.amazonaws.com",
              "s3.${data.aws_region.current.name}.amazonaws.com"
            ]
          }
        }
      }
    ]
  })
}

# Null resource to handle AgentCore deployment, updates, and destruction
resource "null_resource" "agentcore_lifecycle" {
  depends_on = [aws_iam_role.agentcore_execution]
  
  triggers = {
    agent_py_hash        = filemd5("${path.root}/services/chatbot/agent.py")
    deploy_py_hash       = filemd5("${path.root}/services/chatbot/deploy_agent.py")
    requirements_hash    = filemd5("${path.root}/services/chatbot/requirements.txt")
    role_arn            = aws_iam_role.agentcore_execution.arn
    ssm_parameter_name  = var.ssm_parameter_name
  }
  
  # Deploy or update AgentCore Runtime when triggers change
  provisioner "local-exec" {
    working_dir = path.root
    environment = {
      SSM_PARAMETER_NAME = var.ssm_parameter_name
      EXECUTION_ROLE_ARN = aws_iam_role.agentcore_execution.arn
    }
    command = <<-EOT
      set -e
      echo "🚀 Deploying AgentCore Runtime..."
      source .venv/bin/activate
      cd services/chatbot
      python3 deploy_agent.py
      echo "✅ AgentCore deployment completed"
    EOT
  }
  
  # Handle destruction - read runtime info from SSM parameter
  provisioner "local-exec" {
    when        = destroy
    working_dir = path.root
    environment = {
      SSM_PARAMETER_NAME = self.triggers.ssm_parameter_name
    }
    command = <<-EOT
      set -e
      echo "🗑️  Destroying AgentCore resources..."
      source .venv/bin/activate
      cd services/chatbot
      python3 destroy_agent.py
      echo "✅ AgentCore destruction completed"
    EOT
  }
}

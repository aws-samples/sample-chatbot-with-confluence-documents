# Data sources
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# Lambda deployment package
data "archive_file" "ingestion_lambda" {
  type        = "zip"
  source_dir  = "${path.root}/services/ingestion"
  output_path = "${path.root}/.terraform/ingestion_lambda.zip"
}

# IAM role for Lambda
resource "aws_iam_role" "ingestion_lambda" {
  name = "${var.project_name}-${var.environment}-ingestion-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "ingestion_lambda" {
  name = "${var.project_name}-${var.environment}-ingestion-lambda-policy"
  role = aws_iam_role.ingestion_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:*"
      },
      {
        # Justification: Resource is constrained to specific S3 bucket via variable interpolation
        # These permissions are necessary for Lambda to manage Confluence images in S3
        # GetObject: Read existing images for processing
        # PutObject: Upload new/updated images from Confluence
        # DeleteObject: Remove outdated images during incremental sync
        # Scope: Limited to single bucket containing Confluence images only
        # Security: Bucket name is dynamically scoped, no wildcard bucket access
        Effect = "Allow"
        # nosemgrep: terraform.lang.security.iam.no-iam-data-exfiltration
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject"
        ]
        Resource = "arn:aws:s3:::${var.s3_bucket_name}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:Encrypt",
          "kms:GenerateDataKey",
          "kms:DescribeKey"
        ]
        Resource = [
          var.kms_ssm_key_arn,
          var.kms_secrets_key_arn
        ]
        Condition = {
          StringEquals = {
            "kms:ViaService" = [
              "s3.${data.aws_region.current.name}.amazonaws.com",
              "ssm.${data.aws_region.current.name}.amazonaws.com",
              "secretsmanager.${data.aws_region.current.name}.amazonaws.com"
            ]
          }
        }
      },
      {
        # Justification: Resource is constrained to specific secret ARN via variable
        # This permission is necessary for Lambda to retrieve Confluence API token
        # Scope: Read-only access limited to single secret containing Confluence credentials
        # Security: Secret ARN is dynamically scoped, no wildcard secret access
        Effect = "Allow"
        # nosemgrep: terraform.lang.security.iam.no-iam-data-exfiltration
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = var.secrets_manager_arn
      },
      {
        # SSM Parameter Store - Resource-specific permissions
        # Justification: GetParameter and PutParameter support resource-level permissions
        # Scope: Limited to specific configuration and crawl-state parameters only
        # Security: Parameter ARNs are explicitly scoped, no wildcard parameter access
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:PutParameter"
        ]
        Resource = [
          "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter${var.ssm_parameter_name}",
          "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter${var.ssm_parameter_name}-crawl-state"
        ]
      },
      {
        # SSM Parameter Store - Account-level permissions
        # Justification: DescribeParameters is a list/metadata operation that does not support resource-level permissions
        # This is required to retrieve KMS key ID for maintaining SecureString encryption
        # Scope: Read-only metadata access, does not expose parameter values
        # Security: AWS API limitation - DescribeParameters requires wildcard resource per AWS documentation
        # Reference: https://docs.aws.amazon.com/systems-manager/latest/userguide/sysman-paramstore-access.html
        Effect = "Allow"
        # nosemgrep: terraform.lang.security.iam.no-iam-wildcard-resource
        Action = [
          "ssm:DescribeParameters"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:Retrieve",
          "bedrock:StartIngestionJob",
          "bedrock:IngestKnowledgeBaseDocuments"
        ]
        Resource = [
          "arn:aws:bedrock:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:knowledge-base/${var.knowledge_base_id}",
          "arn:aws:bedrock:${data.aws_region.current.name}::foundation-model/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "xray:PutTraceSegments",
          "xray:PutTelemetryRecords"
        ]
        Resource = "*"
      }
    ]
  })
}

# SSM parameter for crawl state
resource "aws_ssm_parameter" "crawl_state" {
  name        = "${var.ssm_parameter_name}-crawl-state"
  type        = "SecureString"
  key_id      = var.kms_ssm_key_arn
  value       = "{}"
  description = "Crawl state tracking for Confluence spaces"
}

# Code signing profile for Lambda
resource "aws_signer_signing_profile" "ingestion_lambda" {
  platform_id = "AWSLambda-SHA384-ECDSA"
  name        = "${replace(var.project_name, "-", "")}${var.environment}ingestionlambda"

  signature_validity_period {
    value = 5
    type  = "YEARS"
  }
}

# Code signing configuration
resource "aws_lambda_code_signing_config" "ingestion" {
  description = "Code signing config for ${var.project_name}-${var.environment}-ingestion"

  allowed_publishers {
    signing_profile_version_arns = [
      aws_signer_signing_profile.ingestion_lambda.arn
    ]
  }

  policies {
    untrusted_artifact_on_deployment = "Warn"
  }
}

# Lambda function
resource "aws_lambda_function" "ingestion" {
  #checkov:skip=CKV_AWS_117:Lambda does not require VPC as it does not access databases directly
  #checkov:skip=CKV_AWS_116:DLQ not needed - retry strategy preferred, data depends on recent Confluence changes
  filename                       = data.archive_file.ingestion_lambda.output_path
  function_name                  = "${var.project_name}-${var.environment}-ingestion"
  role                          = aws_iam_role.ingestion_lambda.arn
  handler                       = "handler.lambda_handler"
  runtime                       = "python3.11"
  timeout                       = var.lambda_timeout
  memory_size                   = var.lambda_memory_size
  source_code_hash              = data.archive_file.ingestion_lambda.output_base64sha256
  reserved_concurrent_executions = 10
  kms_key_arn                   = var.kms_ssm_key_arn
  code_signing_config_arn       = aws_lambda_code_signing_config.ingestion.arn

  environment {
    variables = {
      ATTACHMENTS_BUCKET      = var.s3_bucket_name
      CONFLUENCE_SECRET_ARN   = var.secrets_manager_arn
      CONFIG_PARAMETER        = var.ssm_parameter_name
      CRAWL_STATE_PARAMETER   = aws_ssm_parameter.crawl_state.name
    }
  }

  tracing_config {
    mode = "Active"
  }
}

# EventBridge rule for scheduling
resource "aws_cloudwatch_event_rule" "ingestion_schedule" {
  name                = "${var.project_name}-${var.environment}-ingestion-schedule"
  description         = "Trigger ingestion Lambda every 15 minutes"
  schedule_expression = "rate(15 minutes)"
  state              = "DISABLED"
}

resource "aws_cloudwatch_event_target" "ingestion_lambda" {
  rule      = aws_cloudwatch_event_rule.ingestion_schedule.name
  target_id = "IngestionLambdaTarget"
  arn       = aws_lambda_function.ingestion.arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingestion.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.ingestion_schedule.arn
}

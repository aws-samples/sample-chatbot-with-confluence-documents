data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# S3 bucket for storing images
# nosemgrep: terraform.aws.best-practice.aws-s3-bucket-versioning-not-enabled
resource "aws_s3_bucket" "confluence_images" {
  #checkov:skip=CKV_AWS_144:Cross-region replication not required for this application
  #checkov:skip=CKV2_AWS_62:S3 event notifications not needed for this use case
  bucket        = "${var.project_name}-${var.environment}-images-${random_string.bucket_suffix.result}"
  force_destroy = true
}

resource "random_string" "bucket_suffix" {
  length  = 8
  special = false
  upper   = false
}

# Enable versioning for images bucket to protect against accidental deletions
resource "aws_s3_bucket_versioning" "confluence_images" {
  bucket = aws_s3_bucket.confluence_images.id
  
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "confluence_images" {
  bucket = aws_s3_bucket.confluence_images.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.ssm.id
    }
  }
}

resource "aws_s3_bucket_public_access_block" "confluence_images" {
  bucket = aws_s3_bucket.confluence_images.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# S3 access logging bucket
# nosemgrep: terraform.aws.best-practice.aws-s3-bucket-versioning-not-enabled
resource "aws_s3_bucket" "confluence_images_logs" {
  #checkov:skip=CKV_AWS_21:Versioning not needed for access logs
  #checkov:skip=CKV_AWS_144:Cross-region replication not needed for access logs
  #checkov:skip=CKV2_AWS_62:Event notifications not needed for access logs
  #checkov:skip=CKV2_AWS_61:Lifecycle not needed for access logs bucket
  #checkov:skip=CKV_AWS_145:KMS encryption not required for access logs (low sensitivity)
  bucket        = "${var.project_name}-${var.environment}-images-logs-${random_string.bucket_suffix.result}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "confluence_images_logs" {
  bucket = aws_s3_bucket.confluence_images_logs.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Enable access logging on main bucket
resource "aws_s3_bucket_logging" "confluence_images" {
  bucket = aws_s3_bucket.confluence_images.id

  target_bucket = aws_s3_bucket.confluence_images_logs.id
  target_prefix = "access-logs/"
}

# KMS key for SSM Parameter encryption
resource "aws_kms_key" "ssm" {
  description             = "KMS key for SSM Parameter encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Enable IAM User Permissions"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "Allow Lambda and AgentCore to decrypt via SSM"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action = [
          "kms:Decrypt",
          "kms:DescribeKey"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "kms:ViaService" = "ssm.${data.aws_region.current.name}.amazonaws.com"
          }
        }
      },
      {
        Sid    = "Allow S3 to use the key"
        Effect = "Allow"
        Principal = {
          Service = "s3.amazonaws.com"
        }
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey"
        ]
        Resource = "*"
      },
      {
        Sid    = "Allow Lambda and AgentCore to decrypt S3 objects"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey",
          "kms:DescribeKey"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "kms:ViaService" = "s3.${data.aws_region.current.name}.amazonaws.com"
          }
        }
      }
    ]
  })
}

resource "aws_kms_alias" "ssm" {
  name          = "alias/${var.project_name}-${var.environment}-ssm"
  target_key_id = aws_kms_key.ssm.key_id
}

# KMS key for Secrets Manager encryption
resource "aws_kms_key" "secrets" {
  description             = "KMS key for Secrets Manager encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Enable IAM User Permissions"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "Allow Lambda and AgentCore to decrypt"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action = [
          "kms:Decrypt",
          "kms:DescribeKey"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "kms:ViaService" = "secretsmanager.${data.aws_region.current.name}.amazonaws.com"
          }
        }
      }
    ]
  })
}

resource "aws_kms_alias" "secrets" {
  name          = "alias/${var.project_name}-${var.environment}-secrets"
  target_key_id = aws_kms_key.secrets.key_id
}

# Secrets Manager secret for Confluence API token
resource "aws_secretsmanager_secret" "confluence_token" {
  #checkov:skip=CKV2_AWS_57:Manual rotation - secret managed in Confluence. For production use, implement automatic rotation.
  name                    = "${var.project_name}-${var.environment}-confluence-access-api-token"
  description             = "Confluence API token for ${var.project_name}"
  kms_key_id              = aws_kms_key.secrets.id
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "confluence_token" {
  #checkov:skip=CKV_SECRET_6:Placeholder value only, real token uploaded separately via upload-token.sh script
  secret_id = aws_secretsmanager_secret.confluence_token.id
  secret_string = jsonencode({
    token = "placeholder-token" #checkov:skip=CKV_SECRET_6:Placeholder value only
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# SSM Parameter for configuration
resource "aws_ssm_parameter" "config" {
  name       = "/${var.project_name}/${var.environment}/config"
  type       = "SecureString"
  key_id     = aws_kms_key.ssm.id
  value = jsonencode({
    confluence_base_url    = var.confluence_base_url
    confluence_email       = var.confluence_email
    knowledge_base_id      = var.knowledge_base_id
    data_source_id         = var.data_source_id
    aws_region            = var.aws_region
    confluence_spaces     = var.confluence_spaces
    s3_bucket_name        = aws_s3_bucket.confluence_images.bucket
    knowledge_base_top_n  = var.knowledge_base_top_n
    llm_model_id          = var.llm_model_id
    presigned_url_expiry  = 300
    request_timeout       = 30
  })

  lifecycle {
    ignore_changes = [value]
  }
}

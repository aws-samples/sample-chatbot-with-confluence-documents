variable "project_name" {
  description = "Name of the project"
  type        = string
  default     = "confluence-bedrock"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "dev"
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "ingestion_lambda_timeout" {
  description = "Timeout for ingestion Lambda function in seconds"
  type        = number
  default     = 900
}

variable "ingestion_lambda_memory_size" {
  description = "Memory size for ingestion Lambda function in MB"
  type        = number
  default     = 512
}

variable "chatbot_lambda_timeout" {
  description = "Timeout for chatbot Lambda function in seconds"
  type        = number
  default     = 30
}

variable "chatbot_lambda_memory_size" {
  description = "Memory size for chatbot Lambda function in MB"
  type        = number
  default     = 256
}

variable "confluence_base_url" {
  description = "Confluence base URL"
  type        = string
  default     = ""
}

variable "confluence_email" {
  description = "Confluence email address"
  type        = string
  default     = ""
}

variable "knowledge_base_id" {
  description = "Bedrock Knowledge Base ID"
  type        = string
  default     = ""
}

variable "data_source_id" {
  description = "Bedrock Knowledge Base Data Source ID"
  type        = string
  default     = ""
}

variable "confluence_spaces" {
  description = "List of Confluence spaces to sync"
  type        = list(object({
    key = string
  }))
  default = []
}

variable "knowledge_base_top_n" {
  description = "Number of documents to retrieve from Knowledge Base"
  type        = number
  default     = 3
}

variable "llm_model_id" {
  description = "LLM Model ID for the chatbot"
  type        = string
  default     = ""
}

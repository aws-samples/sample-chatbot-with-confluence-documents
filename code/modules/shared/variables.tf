variable "project_name" {
  description = "Name of the project"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "confluence_base_url" {
  description = "Confluence base URL"
  type        = string
}

variable "confluence_email" {
  description = "Confluence email address"
  type        = string
}

variable "knowledge_base_id" {
  description = "Bedrock Knowledge Base ID"
  type        = string
}

variable "data_source_id" {
  description = "Bedrock Knowledge Base Data Source ID"
  type        = string
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
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

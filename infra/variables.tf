variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Project name prefix used for all resource names"
  type        = string
  default     = "deluxe-v2"
}

variable "alert_email" {
  description = "Email address for CloudWatch alarm notifications"
  type        = string
}

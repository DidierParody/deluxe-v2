output "alb_dns_name" {
  description = "DNS name of the ALB — use this as WEBHOOK_BASE_URL"
  value       = module.alb.dns_name
}

output "ecr_repo_url" {
  description = "ECR repository URL for docker push"
  value       = module.ecr.repo_url
}

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint (private)"
  value       = module.rds.endpoint
}

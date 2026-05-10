output "cluster_name" { value = aws_ecs_cluster.main.name }
output "service_name" { value = aws_ecs_service.web.name }
output "ecs_sg_id"    { value = aws_security_group.ecs.id }

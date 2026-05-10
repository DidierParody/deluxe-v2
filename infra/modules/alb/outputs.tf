output "target_group_arn" { value = aws_lb_target_group.web.arn }
output "alb_sg_id"        { value = aws_security_group.alb.id }
output "dns_name"         { value = aws_lb.main.dns_name }
output "arn_suffix"       { value = aws_lb.main.arn_suffix }
output "tg_arn_suffix"    { value = aws_lb_target_group.web.arn_suffix }

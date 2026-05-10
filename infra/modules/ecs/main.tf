resource "aws_ecs_cluster" "main" {
  name = "${var.project}-cluster"
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
  tags = { Name = "${var.project}-cluster" }
}

resource "aws_security_group" "ecs" {
  name   = "${var.project}-ecs-sg"
  vpc_id = var.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound (DB, Redis, NVIDIA API)"
  }

  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [var.alb_sg_id]
    description     = "HTTP from ALB only"
  }
  tags = { Name = "${var.project}-ecs-sg" }
}

resource "aws_cloudwatch_log_group" "web" {
  name              = "/ecs/${var.project}-web"
  retention_in_days = 14
  tags = { Name = "${var.project}-web-logs" }
}

resource "aws_cloudwatch_log_group" "cron" {
  name              = "/ecs/${var.project}-cron"
  retention_in_days = 7
  tags = { Name = "${var.project}-cron-logs" }
}

resource "aws_ecs_task_definition" "web" {
  family                   = "${var.project}-web"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = var.task_role_arn

  container_definitions = jsonencode([{
    name      = "${var.project}-app"
    image     = var.web_image_uri
    essential = true
    portMappings = [{ containerPort = 8000, protocol = "tcp" }]
    secrets = [
      { name = "DATABASE_URL",           valueFrom = "${var.secrets_arn}:DATABASE_URL::" },
      { name = "TELEGRAM_BOT_TOKEN_CS",  valueFrom = "${var.secrets_arn}:TELEGRAM_BOT_TOKEN_CS::" },
      { name = "TELEGRAM_BOT_TOKEN_AM",  valueFrom = "${var.secrets_arn}:TELEGRAM_BOT_TOKEN_AM::" },
      { name = "WEBHOOK_BASE_URL",       valueFrom = "${var.secrets_arn}:WEBHOOK_BASE_URL::" },
      { name = "WEBHOOK_SECRET_TOKEN",   valueFrom = "${var.secrets_arn}:WEBHOOK_SECRET_TOKEN::" },
      { name = "NVIDIA_API_KEY",         valueFrom = "${var.secrets_arn}:NVIDIA_API_KEY::" },
      { name = "UPSTASH_REDIS_REST_URL", valueFrom = "${var.secrets_arn}:UPSTASH_REDIS_REST_URL::" },
      { name = "UPSTASH_REDIS_REST_TOKEN", valueFrom = "${var.secrets_arn}:UPSTASH_REDIS_REST_TOKEN::" }
    ]
    environment = [
      { name = "REDIS_MEMORY_ENABLED",           value = "true" },
      { name = "ENABLE_BACKGROUND_SCHEDULER",    value = "false" }
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.web.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "web"
      }
    }
  }])
}

resource "aws_ecs_service" "web" {
  name                   = "${var.project}-web"
  cluster                = aws_ecs_cluster.main.id
  task_definition        = aws_ecs_task_definition.web.arn
  desired_count          = 1
  launch_type            = "FARGATE"
  enable_execute_command = true

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = var.alb_target_group_arn
    container_name   = "${var.project}-app"
    container_port   = 8000
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  lifecycle {
    ignore_changes = [task_definition]   # Managed by CI/CD
  }
}

# ── Cron task definition (shared image, different entrypoint arg) ─────────────
resource "aws_ecs_task_definition" "cron" {
  family                   = "${var.project}-cron"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = var.task_role_arn

  container_definitions = jsonencode([{
    name      = "${var.project}-cron"
    image     = var.cron_image_uri
    essential = true
    command   = []   # Overridden per-schedule by EventBridge input
    secrets = [
      { name = "DATABASE_URL", valueFrom = "${var.secrets_arn}:DATABASE_URL::" }
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.cron.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "cron"
      }
    }
  }])
}

# ── EventBridge Schedules (replaces Render cron + APScheduler) ───────────────
resource "aws_iam_role" "scheduler" {
  name = "${var.project}-scheduler"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "scheduler.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "scheduler_ecs" {
  name = "run-ecs-tasks"
  role = aws_iam_role.scheduler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ecs:RunTask", "iam:PassRole"]
      Resource = "*"
    }]
  })
}

locals {
  cron_jobs = {
    finalizar_eventos = {
      schedule    = "rate(5 minutes)"
      job_name    = "finalizar_eventos_expirados"
    }
    liberar_mesas = {
      schedule    = "rate(10 minutes)"
      job_name    = "liberar_mesas_expiradas"
    }
  }
}

resource "aws_scheduler_schedule" "cron" {
  for_each = local.cron_jobs

  name       = "${var.project}-${each.key}"
  group_name = "default"

  flexible_time_window { mode = "OFF" }
  schedule_expression = each.value.schedule

  target {
    arn      = aws_ecs_cluster.main.arn
    role_arn = aws_iam_role.scheduler.arn

    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.cron.arn
      launch_type         = "FARGATE"
      task_count          = 1

      network_configuration {
        subnets          = var.private_subnet_ids
        security_groups  = [aws_security_group.ecs.id]
        assign_public_ip = false
      }
    }

    input = jsonencode({
      containerOverrides = [{
        name    = "${var.project}-cron"
        command = [each.value.job_name]
      }]
    })
  }
}

resource "aws_db_subnet_group" "main" {
  name       = "${var.project}-db-subnet"
  subnet_ids = var.private_subnet_ids
  tags = { Name = "${var.project}-db-subnet-group" }
}

resource "aws_security_group" "rds" {
  name   = "${var.project}-rds-sg"
  vpc_id = var.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.ecs_sg_id]
    description     = "PostgreSQL from ECS tasks only"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { Name = "${var.project}-rds-sg" }
}

resource "aws_db_instance" "main" {
  identifier              = "${var.project}-postgres"
  engine                  = "postgres"
  engine_version          = "16"
  instance_class          = "db.t4g.micro"
  allocated_storage       = 20
  storage_encrypted       = true
  db_name                 = "deluxe"
  username                = "deluxe_admin"
  manage_master_user_password = true   # Rotated by Secrets Manager automatically
  db_subnet_group_name    = aws_db_subnet_group.main.name
  vpc_security_group_ids  = [aws_security_group.rds.id]
  publicly_accessible     = false
  skip_final_snapshot     = false
  final_snapshot_identifier = "${var.project}-final-snapshot"
  backup_retention_period = 0
  multi_az                = false   # Enable for production when budget allows

  tags = { Name = "${var.project}-postgres" }
}

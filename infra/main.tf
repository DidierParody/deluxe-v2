terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  backend "s3" {
    bucket         = "deluxe-v2-tfstate-352602573484"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "deluxe-v2-tflock"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region
}

module "networking" {
  source     = "./modules/networking"
  aws_region = var.aws_region
  project    = var.project
}

module "ecr" {
  source  = "./modules/ecr"
  project = var.project
}

module "iam" {
  source      = "./modules/iam"
  project     = var.project
  ecr_arn     = module.ecr.repo_arn
  secrets_arn = module.secrets.secrets_arn
}

module "secrets" {
  source  = "./modules/secrets"
  project = var.project
}

module "rds" {
  source             = "./modules/rds"
  project            = var.project
  vpc_id             = module.networking.vpc_id
  private_subnet_ids = module.networking.private_subnet_ids
  ecs_sg_id          = module.ecs.ecs_sg_id
}

module "alb" {
  source            = "./modules/alb"
  project           = var.project
  vpc_id            = module.networking.vpc_id
  public_subnet_ids = module.networking.public_subnet_ids
}

module "ecs" {
  source                   = "./modules/ecs"
  project                  = var.project
  aws_region               = var.aws_region
  private_subnet_ids       = module.networking.private_subnet_ids
  vpc_id                   = module.networking.vpc_id
  alb_target_group_arn     = module.alb.target_group_arn
  alb_sg_id                = module.alb.alb_sg_id
  task_execution_role_arn  = module.iam.task_execution_role_arn
  task_role_arn            = module.iam.task_role_arn
  web_image_uri            = "${module.ecr.repo_url}:latest"
  cron_image_uri           = "${module.ecr.repo_url}:cron-latest"
  secrets_arn              = module.secrets.secrets_arn
}

module "monitoring" {
  source          = "./modules/monitoring"
  project         = var.project
  ecs_cluster     = module.ecs.cluster_name
  ecs_service     = module.ecs.service_name
  alb_arn_suffix  = module.alb.arn_suffix
  tg_arn_suffix   = module.alb.tg_arn_suffix
  alert_email     = var.alert_email
}

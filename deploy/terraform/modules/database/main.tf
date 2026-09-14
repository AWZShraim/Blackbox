# Hot trace store (Section 9). engine_mode picks between two genuinely
# different resource types, not a size variant of the same one — a
# db.t4g.micro RDS instance for the demo profile (cheap, single-AZ,
# acceptable for a non-critical public demo) and Aurora Serverless v2 for
# the reference profile (multi-AZ, scales to zero-ish, the spec-correct
# choice for a real deployment). Both live in the private, no-egress
# database subnets from modules/network — Postgres never needs to reach
# the internet.

resource "random_password" "db" {
  length  = 24
  special = false # simplifies embedding in a DATABASE_URL without escaping
}

resource "aws_db_subnet_group" "this" {
  name       = "${var.name_prefix}-db-subnets"
  subnet_ids = var.subnet_ids
}

resource "aws_security_group" "db" {
  name        = "${var.name_prefix}-db-sg"
  description = "Allows Postgres access from the mediator and recorder services only"
  vpc_id      = var.vpc_id

  ingress {
    description     = "Postgres from mediator/recorder"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = var.allowed_security_group_ids
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { Name = "${var.name_prefix}-db-sg" }
}

# -- demo profile: single RDS instance ---------------------------------------

resource "aws_db_instance" "rds" {
  count = var.engine_mode == "rds" ? 1 : 0

  identifier             = "${var.name_prefix}-pg"
  engine                 = "postgres"
  engine_version         = "16"
  instance_class         = "db.t4g.micro"
  allocated_storage      = 20
  storage_type           = "gp3"
  db_name                = var.database_name
  username               = "blackbox"
  password               = random_password.db.result
  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.db.id]
  multi_az               = false
  publicly_accessible    = false
  skip_final_snapshot    = true # this is a teardown exercise (Section 8/user requirement), not a permanent environment
  deletion_protection    = false
  apply_immediately      = true
  tags                   = { Name = "${var.name_prefix}-pg" }
}

# -- reference profile: Aurora Serverless v2, multi-AZ -----------------------

resource "aws_rds_cluster" "aurora" {
  count = var.engine_mode == "aurora_serverless_v2" ? 1 : 0

  cluster_identifier     = "${var.name_prefix}-aurora"
  engine                 = "aurora-postgresql"
  engine_mode            = "provisioned" # required for Serverless v2 scaling config
  engine_version         = "15.4"
  database_name          = var.database_name
  master_username        = "blackbox"
  master_password        = random_password.db.result
  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.db.id]
  skip_final_snapshot    = true
  deletion_protection    = false
  apply_immediately      = true

  serverlessv2_scaling_configuration {
    min_capacity = 0.5
    max_capacity = 4
  }
  tags = { Name = "${var.name_prefix}-aurora" }
}

resource "aws_rds_cluster_instance" "aurora" {
  count              = var.engine_mode == "aurora_serverless_v2" ? var.az_count_for_aurora : 0
  cluster_identifier = aws_rds_cluster.aurora[0].id
  instance_class     = "db.serverless"
  engine             = aws_rds_cluster.aurora[0].engine
  engine_version     = aws_rds_cluster.aurora[0].engine_version
  tags               = { Name = "${var.name_prefix}-aurora-${count.index}" }
}

locals {
  endpoint = var.engine_mode == "rds" ? aws_db_instance.rds[0].address : aws_rds_cluster.aurora[0].endpoint
  port     = var.engine_mode == "rds" ? aws_db_instance.rds[0].port : aws_rds_cluster.aurora[0].port
}

# Section 9's network posture, made structural rather than merely
# discouraged: the "public" subnets below hold the always-on services
# (mediator, recorder, investigator, demo orchestrator) and the ALB — they
# have public IPs and an internet gateway route instead of a NAT gateway,
# which is a deliberate cost trade (a NAT gateway alone runs ~$32/mo,
# exceeding the entire demo budget on its own). The "agent" subnets are
# where ephemeral per-scenario agent tasks run: no NAT, no internet
# gateway route, no public IP — their route table has no 0.0.0.0/0 route
# at all, so "no NAT gateway" is a routing-table fact, not a security-group
# promise. Their only reachable peer is the mediator, over the VPC's
# internal network, via the security group rule in modules/iam.

data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_region" "current" {}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = "${var.name_prefix}-vpc" }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${var.name_prefix}-igw" }
}

# -- public subnets: ALB + always-on services --------------------------------

resource "aws_subnet" "public" {
  count                   = var.az_count
  vpc_id                  = aws_vpc.this.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true
  tags                    = { Name = "${var.name_prefix}-public-${count.index}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }
  tags = { Name = "${var.name_prefix}-public-rt" }
}

resource "aws_route_table_association" "public" {
  count          = var.az_count
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# -- agent subnets: ephemeral per-scenario tasks, no NAT, no egress -----------

resource "aws_subnet" "agent" {
  count             = var.az_count
  vpc_id            = aws_vpc.this.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, 100 + count.index)
  availability_zone = data.aws_availability_zones.available.names[count.index]
  tags              = { Name = "${var.name_prefix}-agent-${count.index}" }
}

# Deliberately no routes beyond the VPC's implicit local route — no NAT
# gateway resource exists anywhere in this module, and none is referenced
# here. An agent task in this subnet can reach other things in the VPC
# (the mediator's service) and nothing else, full stop.
resource "aws_route_table" "agent" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${var.name_prefix}-agent-rt-no-egress" }
}

resource "aws_route_table_association" "agent" {
  count          = var.az_count
  subnet_id      = aws_subnet.agent[count.index].id
  route_table_id = aws_route_table.agent.id
}

# -- database subnets (private, VPC-internal only, same posture as agent) ---

resource "aws_subnet" "database" {
  count             = var.az_count
  vpc_id            = aws_vpc.this.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, 200 + count.index)
  availability_zone = data.aws_availability_zones.available.names[count.index]
  tags              = { Name = "${var.name_prefix}-db-${count.index}" }
}

resource "aws_route_table" "database" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${var.name_prefix}-db-rt-no-egress" }
}

resource "aws_route_table_association" "database" {
  count          = var.az_count
  subnet_id      = aws_subnet.database[count.index].id
  route_table_id = aws_route_table.database.id
}

# -- PrivateLink (reference profile only) ------------------------------------

resource "aws_security_group" "vpc_endpoints" {
  count       = var.enable_privatelink ? 1 : 0
  name        = "${var.name_prefix}-vpce-sg"
  description = "Allows the public-subnet services to reach VPC interface endpoints on 443"
  vpc_id      = aws_vpc.this.id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { Name = "${var.name_prefix}-vpce-sg" }
}

locals {
  interface_endpoint_services = var.enable_privatelink ? toset([
    "ecr.api", "ecr.dkr", "secretsmanager", "logs", "sts", "bedrock-runtime",
  ]) : toset([])
}

resource "aws_vpc_endpoint" "interface" {
  for_each            = local.interface_endpoint_services
  vpc_id              = aws_vpc.this.id
  service_name        = "com.amazonaws.${data.aws_region.current.name}.${each.value}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.public[*].id
  security_group_ids  = [aws_security_group.vpc_endpoints[0].id]
  private_dns_enabled = true
  tags                = { Name = "${var.name_prefix}-vpce-${each.value}" }
}

resource "aws_vpc_endpoint" "s3_gateway" {
  count             = var.enable_privatelink ? 1 : 0
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${data.aws_region.current.name}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.public.id, aws_route_table.database.id, aws_route_table.agent.id]
  tags              = { Name = "${var.name_prefix}-vpce-s3" }
}

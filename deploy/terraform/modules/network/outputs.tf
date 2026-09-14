output "vpc_id" { value = aws_vpc.this.id }
output "vpc_cidr" { value = var.vpc_cidr }
output "public_subnet_ids" { value = aws_subnet.public[*].id }
output "agent_subnet_ids" { value = aws_subnet.agent[*].id }
output "database_subnet_ids" { value = aws_subnet.database[*].id }

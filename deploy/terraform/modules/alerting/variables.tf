variable "name_prefix" { type = string }
variable "monthly_budget_usd" { type = number }
variable "budget_alert_email" {
  type    = string
  default = ""
}

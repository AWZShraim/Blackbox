variable "name_prefix" { type = string }
variable "object_lock_mode" {
  type = string
  validation {
    condition     = contains(["GOVERNANCE", "COMPLIANCE"], var.object_lock_mode)
    error_message = "object_lock_mode must be GOVERNANCE or COMPLIANCE."
  }
}
variable "object_lock_retention_days" { type = number }

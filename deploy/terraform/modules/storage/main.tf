# Immutable, long-term archive (Section 6.3, Section 9). Object Lock
# requires versioning, and requires being enabled at bucket CREATION time —
# it cannot be turned on for an existing bucket, which is why this is one
# resource with object_lock_enabled set up front rather than a bucket plus
# a bolted-on policy.
#
# GOVERNANCE mode (demo profile): an admin with s3:BypassGovernanceRetention
# can still delete/overwrite locked objects, which is what lets `make
# destroy` actually empty this bucket. COMPLIANCE mode (reference profile):
# nobody can, not even the account root, until the retention period
# expires — the spec-correct posture for a real deployment's evidence
# store, and exactly why the reference profile is validated but never
# applied here (see the module-level comment in main.tf).

resource "random_id" "suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "archive" {
  bucket              = "${var.name_prefix}-trace-archive-${random_id.suffix.hex}"
  object_lock_enabled = true
  tags                = { Name = "${var.name_prefix}-trace-archive" }
}

resource "aws_s3_bucket_versioning" "archive" {
  bucket = aws_s3_bucket.archive.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_object_lock_configuration" "archive" {
  bucket = aws_s3_bucket.archive.id
  rule {
    default_retention {
      mode = var.object_lock_mode
      days = var.object_lock_retention_days
    }
  }
  depends_on = [aws_s3_bucket_versioning.archive]
}

resource "aws_s3_bucket_public_access_block" "archive" {
  bucket                  = aws_s3_bucket.archive.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "archive" {
  bucket = aws_s3_bucket.archive.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

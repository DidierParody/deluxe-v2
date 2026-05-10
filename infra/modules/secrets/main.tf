# One secret object containing all sensitive env vars as a JSON map.
# Values are loaded manually via: aws secretsmanager put-secret-value --secret-id <arn> --secret-string '{"KEY":"value"}'
resource "aws_secretsmanager_secret" "app" {
  name                    = "${var.project}/app"
  recovery_window_in_days = 7
  tags = { Name = "${var.project}-secrets" }
}

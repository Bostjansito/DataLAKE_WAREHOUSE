# Fase 0: alerta de costos. AWS Budgets permite 2 presupuestos gratuitos por cuenta.
# Solo se crea si se define budget_alert_email.

resource "aws_budgets_budget" "monthly" {
  count = var.budget_alert_email == "" ? 0 : 1

  name         = "${var.project_name}-${var.environment}-mensual"
  budget_type  = "COST"
  limit_amount = tostring(var.budget_limit_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 50
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_alert_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.budget_alert_email]
  }
}

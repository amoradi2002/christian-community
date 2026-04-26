from flask import Blueprint, render_template, request
from bot.alerts.manager import AlertManager

alerts_bp = Blueprint("alerts", __name__)


@alerts_bp.route("/alerts")
def alerts_page():
    symbol = request.args.get("symbol")
    limit = int(request.args.get("limit", 50))
    alert_mgr = AlertManager()
    alerts = alert_mgr.get_alert_history(limit=limit, symbol=symbol)
    return render_template("alerts.html", alerts=alerts, filter_symbol=symbol)

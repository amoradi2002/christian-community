from flask import Blueprint, render_template
from bot.engine.performance import get_strategy_stats, get_open_positions

performance_bp = Blueprint("performance", __name__)


@performance_bp.route("/performance")
def performance_page():
    stats = get_strategy_stats()
    positions = get_open_positions()
    return render_template("performance.html", stats=stats, positions=positions)

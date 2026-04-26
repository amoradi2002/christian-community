import json
from flask import Blueprint, render_template, request, redirect, url_for, flash
from bot.strategies.store import list_strategies, save_strategy, toggle_strategy, delete_strategy

strategies_bp = Blueprint("strategies", __name__)


@strategies_bp.route("/strategies")
def strategies_page():
    strategies = list_strategies(active_only=False)
    return render_template("strategies.html", strategies=strategies)


@strategies_bp.route("/strategies/add", methods=["POST"])
def add_strategy():
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    signal = request.form.get("signal", "BUY")
    symbols = [s.strip() for s in request.form.get("symbols", "").split(",") if s.strip()]

    # Parse conditions from form
    conditions = []
    indicators = request.form.getlist("indicator")
    operators = request.form.getlist("operator")
    values = request.form.getlist("cond_value")
    refs = request.form.getlist("ref")

    for i in range(len(indicators)):
        if not indicators[i]:
            continue
        cond = {"indicator": indicators[i], "operator": operators[i]}
        if refs[i]:
            cond["ref"] = refs[i]
        else:
            cond["value"] = float(values[i]) if values[i] else 0
        conditions.append(cond)

    if not name or not conditions:
        flash("Strategy name and at least one condition required.", "error")
        return redirect(url_for("strategies.strategies_page"))

    rules = {
        "name": name,
        "description": description,
        "conditions": conditions,
        "signal": signal,
        "symbols": symbols,
    }

    save_strategy(name, "mentorship", description, rules)
    flash(f"Strategy '{name}' added!", "success")
    return redirect(url_for("strategies.strategies_page"))


@strategies_bp.route("/strategies/<int:strategy_id>/toggle", methods=["POST"])
def toggle(strategy_id):
    is_active = request.form.get("is_active") == "1"
    toggle_strategy(strategy_id, is_active)
    return redirect(url_for("strategies.strategies_page"))


@strategies_bp.route("/strategies/<int:strategy_id>/delete", methods=["POST"])
def delete(strategy_id):
    delete_strategy(strategy_id)
    flash("Strategy deleted.", "success")
    return redirect(url_for("strategies.strategies_page"))

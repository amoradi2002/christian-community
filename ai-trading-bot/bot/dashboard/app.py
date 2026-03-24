from flask import Flask
from bot.config.settings import CONFIG


def create_app():
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.secret_key = "trading-bot-secret-key-change-me"

    from bot.dashboard.routes.alerts import alerts_bp
    from bot.dashboard.routes.strategies import strategies_bp
    from bot.dashboard.routes.performance import performance_bp
    from bot.dashboard.routes.backtest import backtest_bp
    from bot.dashboard.routes.api import api_bp
    from bot.dashboard.routes.youtube import youtube_bp

    app.register_blueprint(alerts_bp)
    app.register_blueprint(strategies_bp)
    app.register_blueprint(backtest_bp)
    app.register_blueprint(performance_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(youtube_bp)

    @app.route("/")
    def index():
        from flask import render_template
        from bot.alerts.manager import AlertManager
        from bot.engine.performance import get_open_positions, get_strategy_stats

        alert_mgr = AlertManager()
        recent_alerts = alert_mgr.get_alert_history(limit=10)
        open_positions = get_open_positions()
        stats = get_strategy_stats()

        return render_template(
            "dashboard.html",
            alerts=recent_alerts,
            positions=open_positions,
            stats=stats,
        )

    return app

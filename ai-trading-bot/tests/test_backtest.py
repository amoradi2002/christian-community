"""Tests for backtesting engine."""
import pytest
from bot.backtest.portfolio import Portfolio, Trade, Position, EquityPoint
from bot.backtest.report import generate_report, BacktestResult


class TestPosition:
    def test_long_unrealized_pnl(self):
        pos = Position(symbol="AAPL", shares=10, entry_price=100.0,
                       entry_date="2024-01-01", strategy_name="test")
        assert pos.unrealized_pnl(110.0) == 100.0
        assert pos.unrealized_pnl(90.0) == -100.0

    def test_short_unrealized_pnl(self):
        pos = Position(symbol="AAPL", shares=10, entry_price=100.0,
                       entry_date="2024-01-01", strategy_name="test", side="short")
        assert pos.unrealized_pnl(90.0) == 100.0
        assert pos.unrealized_pnl(110.0) == -100.0

    def test_trailing_stop_long(self):
        pos = Position(symbol="AAPL", shares=10, entry_price=100.0,
                       entry_date="2024-01-01", strategy_name="test",
                       trailing_stop_pct=5.0, highest_price=100.0, stop_loss=95.0)
        # Price moves up
        pos.update_trailing_stop(110.0)
        assert pos.highest_price == 110.0
        assert pos.stop_loss == pytest.approx(104.5, rel=1e-2)

    def test_stop_loss_trigger_long(self):
        pos = Position(symbol="AAPL", shares=10, entry_price=100.0,
                       entry_date="2024-01-01", strategy_name="test",
                       stop_loss=95.0)
        assert pos.check_stop_triggered(94.0, 101.0) == "stop_loss"
        assert pos.check_stop_triggered(96.0, 101.0) is None

    def test_take_profit_trigger_long(self):
        pos = Position(symbol="AAPL", shares=10, entry_price=100.0,
                       entry_date="2024-01-01", strategy_name="test",
                       take_profit=110.0)
        assert pos.check_stop_triggered(99.0, 111.0) == "take_profit"
        assert pos.check_stop_triggered(99.0, 109.0) is None


class TestPortfolio:
    def test_initial_state(self):
        p = Portfolio(cash=10000.0)
        assert p.cash == 10000.0
        assert len(p.positions) == 0
        assert len(p.trades) == 0

    def test_buy(self):
        p = Portfolio(cash=10000.0, slippage_pct=0.0, commission_per_trade=0.0)
        result = p.buy("AAPL", 150.0, "2024-01-01", "test_strategy")
        assert result is True
        assert "AAPL" in p.positions
        assert p.cash < 10000.0

    def test_buy_duplicate_blocked(self):
        p = Portfolio(cash=10000.0, slippage_pct=0.0)
        p.buy("AAPL", 150.0, "2024-01-01")
        result = p.buy("AAPL", 155.0, "2024-01-02")  # Already holding
        assert result is False

    def test_sell(self):
        p = Portfolio(cash=10000.0, slippage_pct=0.0, commission_per_trade=0.0)
        p.buy("AAPL", 150.0, "2024-01-01", "test")
        cash_after_buy = p.cash
        result = p.sell("AAPL", 160.0, "2024-01-10")
        assert result is True
        assert "AAPL" not in p.positions
        assert p.cash > cash_after_buy
        assert len(p.trades) == 1

    def test_sell_nonexistent(self):
        p = Portfolio(cash=10000.0)
        result = p.sell("AAPL", 150.0, "2024-01-01")
        assert result is False

    def test_trade_pnl_positive(self):
        p = Portfolio(cash=10000.0, slippage_pct=0.0, commission_per_trade=0.0)
        p.buy("AAPL", 100.0, "2024-01-01")
        p.sell("AAPL", 110.0, "2024-01-10")
        trade = p.trades[0]
        assert trade.pnl_pct > 0

    def test_trade_pnl_negative(self):
        p = Portfolio(cash=10000.0, slippage_pct=0.0, commission_per_trade=0.0)
        p.buy("AAPL", 100.0, "2024-01-01")
        p.sell("AAPL", 90.0, "2024-01-10")
        trade = p.trades[0]
        assert trade.pnl_pct < 0

    def test_total_value(self):
        p = Portfolio(cash=10000.0, slippage_pct=0.0, commission_per_trade=0.0)
        p.buy("AAPL", 100.0, "2024-01-01", allocation_pct=10.0)
        total = p.total_value({"AAPL": 100.0})
        assert abs(total - 10000.0) < 1.0  # Should be ~same

    def test_equity_curve(self):
        p = Portfolio(cash=10000.0)
        p.snapshot_equity("2024-01-01", {"AAPL": 150.0})
        assert len(p.equity_curve) == 1
        assert p.equity_curve[0].equity == 10000.0

    def test_max_positions_enforced(self):
        p = Portfolio(cash=100000.0, max_positions=2, slippage_pct=0.0)
        assert p.buy("AAPL", 100.0, "2024-01-01") is True
        assert p.buy("GOOG", 100.0, "2024-01-01") is True
        assert p.buy("MSFT", 100.0, "2024-01-01") is False

    def test_short_position(self):
        p = Portfolio(cash=10000.0, slippage_pct=0.0, commission_per_trade=0.0)
        result = p.sell_short("AAPL", 100.0, "2024-01-01", "test")
        assert result is True
        assert "AAPL" in p.positions
        assert p.positions["AAPL"].side == "short"

    def test_get_exposure(self):
        p = Portfolio(cash=10000.0, slippage_pct=0.0, commission_per_trade=0.0,
                      position_size_pct=50.0)
        p.buy("AAPL", 100.0, "2024-01-01")
        exposure = p.get_exposure({"AAPL": 100.0})
        assert exposure["long_pct"] > 0
        assert exposure["short_pct"] == 0.0

    def test_check_stops(self):
        p = Portfolio(cash=10000.0, slippage_pct=0.0, commission_per_trade=0.0)
        p.buy("AAPL", 100.0, "2024-01-01", stop_loss=90.0)
        # Price drops below stop
        closed = p.check_stops({"AAPL": 89.0}, "2024-01-05",
                               candle_data={"AAPL": {"high": 95.0, "low": 88.0}})
        assert len(closed) == 1
        assert closed[0].exit_reason == "stop_loss"
        assert "AAPL" not in p.positions


class TestReport:
    def test_no_trades_report(self):
        p = Portfolio(cash=10000.0)
        report = generate_report(p, "AAPL", "test")
        assert report.total_trades == 0

    def test_report_with_trades(self):
        p = Portfolio(cash=10000.0, slippage_pct=0.0, commission_per_trade=0.0)
        p.buy("AAPL", 100.0, "2024-01-01", "test_strategy")
        p.snapshot_equity("2024-01-01", {"AAPL": 100.0})
        p.sell("AAPL", 110.0, "2024-02-01")
        p.snapshot_equity("2024-02-01", {"AAPL": 110.0})
        report = generate_report(p, "AAPL", "test_strategy")
        assert report.total_trades == 1
        assert report.wins == 1
        assert report.win_rate == 100.0
        assert report.total_return_pct > 0

    def test_report_metrics_present(self):
        p = Portfolio(cash=10000.0, slippage_pct=0.0, commission_per_trade=0.0)
        p.buy("AAPL", 100.0, "2024-01-01")
        p.snapshot_equity("2024-01-01", {"AAPL": 100.0})
        p.sell("AAPL", 95.0, "2024-01-15")
        p.snapshot_equity("2024-01-15", {"AAPL": 95.0})
        p.buy("AAPL", 95.0, "2024-01-20")
        p.snapshot_equity("2024-01-20", {"AAPL": 95.0})
        p.sell("AAPL", 105.0, "2024-02-01")
        p.snapshot_equity("2024-02-01", {"AAPL": 105.0})
        report = generate_report(p, "AAPL", "test")
        assert report.sharpe_ratio is not None
        assert report.max_drawdown_pct is not None
        assert report.avg_win_pct is not None
        assert report.avg_loss_pct is not None

    def test_to_dict(self):
        p = Portfolio(cash=10000.0, slippage_pct=0.0, commission_per_trade=0.0)
        p.buy("AAPL", 100.0, "2024-01-01")
        p.snapshot_equity("2024-01-01", {"AAPL": 100.0})
        p.sell("AAPL", 110.0, "2024-02-01")
        p.snapshot_equity("2024-02-01", {"AAPL": 110.0})
        report = generate_report(p, "AAPL", "test")
        d = report.to_dict()
        assert "total_return_pct" in d
        assert "sharpe_ratio" in d
        assert "trades" in d

    def test_summary_text(self):
        p = Portfolio(cash=10000.0, slippage_pct=0.0, commission_per_trade=0.0)
        p.buy("AAPL", 100.0, "2024-01-01")
        p.snapshot_equity("2024-01-01", {"AAPL": 100.0})
        p.sell("AAPL", 110.0, "2024-02-01")
        p.snapshot_equity("2024-02-01", {"AAPL": 110.0})
        report = generate_report(p, "AAPL", "test")
        text = report.summary_text()
        assert "Backtest" in text
        assert "Total Return" in text

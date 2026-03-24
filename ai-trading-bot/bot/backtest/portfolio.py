from dataclasses import dataclass, field


@dataclass
class Trade:
    symbol: str
    action: str
    entry_price: float
    entry_date: str
    exit_price: float = 0.0
    exit_date: str = ""
    pnl_pct: float = 0.0
    strategy_name: str = ""


@dataclass
class Portfolio:
    cash: float = 10000.0
    positions: dict = field(default_factory=dict)  # symbol -> {shares, entry_price, entry_date}
    trades: list = field(default_factory=list)
    equity_curve: list = field(default_factory=list)

    def buy(self, symbol, price, date, strategy_name="", allocation_pct=0.1):
        if symbol in self.positions:
            return False

        amount = self.cash * allocation_pct
        shares = amount / price
        self.cash -= amount
        self.positions[symbol] = {
            "shares": shares,
            "entry_price": price,
            "entry_date": date,
            "strategy_name": strategy_name,
        }
        return True

    def sell(self, symbol, price, date):
        if symbol not in self.positions:
            return False

        pos = self.positions.pop(symbol)
        shares = pos["shares"]
        entry_price = pos["entry_price"]
        proceeds = shares * price
        self.cash += proceeds

        pnl_pct = ((price - entry_price) / entry_price) * 100

        self.trades.append(Trade(
            symbol=symbol,
            action="BUY",
            entry_price=entry_price,
            entry_date=pos["entry_date"],
            exit_price=price,
            exit_date=date,
            pnl_pct=pnl_pct,
            strategy_name=pos.get("strategy_name", ""),
        ))
        return True

    def total_value(self, current_prices: dict) -> float:
        value = self.cash
        for symbol, pos in self.positions.items():
            price = current_prices.get(symbol, pos["entry_price"])
            value += pos["shares"] * price
        return value

    def snapshot_equity(self, date, current_prices):
        self.equity_curve.append({
            "date": date,
            "equity": self.total_value(current_prices),
        })

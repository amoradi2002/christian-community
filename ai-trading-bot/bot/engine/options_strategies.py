"""
Options Strategy Engine - Automated strategy selection and risk-aware sizing.

Supports:
- Long calls/puts (bullish/bearish directional)
- Vertical spreads (defined risk, lower cost)
- Iron condors (neutral, collect premium)
- Covered calls (income on shares you own)
- Cash-secured puts (get paid to wait for entry)
- Straddles/strangles (play volatility, not direction)

The engine picks the best strategy based on:
- Your account size and risk budget
- Current IV rank (high IV = sell premium, low IV = buy options)
- Signal direction and confidence
- Days to expiration sweet spot
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from bot.data.options import (
    get_options_chain, get_option_quote, OptionsChain, OptionContract,
)
from bot.engine.risk_manager import RiskManager, load_profile


@dataclass
class OptionsSetup:
    """A complete options trade recommendation."""
    strategy_name: str           # "long_call", "bull_call_spread", etc.
    description: str             # Human readable explanation
    direction: str               # "bullish", "bearish", "neutral"
    contracts: list[dict] = field(default_factory=list)  # Legs of the trade
    max_profit: float = 0.0      # Best case scenario
    max_loss: float = 0.0        # Worst case (your actual risk)
    breakeven: float = 0.0       # Stock price where you break even
    probability_of_profit: float = 0.0  # Estimated based on delta
    capital_required: float = 0.0       # Cash needed to enter
    risk_reward_ratio: float = 0.0
    suggested_exit_profit_pct: float = 50.0  # Take profit at 50% of max profit
    suggested_exit_loss_pct: float = 100.0   # Cut loss at 100% (let it expire worthless)
    days_to_expiry: int = 0
    iv_rank: float = 0.0         # 0-100, where current IV sits vs past year
    why: list[str] = field(default_factory=list)  # Reasons for this strategy
    can_trade: bool = True
    block_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "description": self.description,
            "direction": self.direction,
            "contracts": self.contracts,
            "max_profit": self.max_profit,
            "max_loss": self.max_loss,
            "breakeven": self.breakeven,
            "probability_of_profit": self.probability_of_profit,
            "capital_required": self.capital_required,
            "risk_reward_ratio": self.risk_reward_ratio,
            "suggested_exit_profit_pct": self.suggested_exit_profit_pct,
            "suggested_exit_loss_pct": self.suggested_exit_loss_pct,
            "days_to_expiry": self.days_to_expiry,
            "iv_rank": self.iv_rank,
            "why": self.why,
            "can_trade": self.can_trade,
            "block_reason": self.block_reason,
        }


class OptionsEngine:
    """
    Picks the right options strategy for your situation.
    Takes into account account size, IV, direction, and risk budget.
    """

    def __init__(self):
        self.rm = RiskManager()
        self.profile = self.rm.profile

    def recommend(
        self,
        symbol: str,
        direction: str = "bullish",
        confidence: float = 0.7,
        target_dte: int = 30,
    ) -> list[OptionsSetup]:
        """
        Get options strategy recommendations for a symbol.

        Args:
            symbol: Stock ticker
            direction: "bullish", "bearish", or "neutral"
            confidence: 0-1 signal confidence
            target_dte: Ideal days to expiration (30-45 is the sweet spot)

        Returns list of setups ranked by suitability for your account.
        """
        # Fetch the chain
        expiry_min = datetime.now().strftime("%Y-%m-%d")
        expiry_max = (datetime.now() + timedelta(days=target_dte + 15)).strftime("%Y-%m-%d")

        try:
            chain = get_options_chain(symbol, expiry_min=expiry_min, expiry_max=expiry_max)
        except Exception as e:
            return [OptionsSetup(
                strategy_name="error", description=f"Could not fetch options chain: {e}",
                direction=direction, can_trade=False, block_reason=str(e),
            )]

        if not chain.calls and not chain.puts:
            return [OptionsSetup(
                strategy_name="error", description="No options data available",
                direction=direction, can_trade=False, block_reason="Empty chain",
            )]

        price = chain.underlying_price
        risk_budget = self.rm.profile.risk_per_trade_dollars()
        capital = self.profile.current_capital

        # Estimate IV rank (simplified: compare ATM IV to historical)
        iv_rank = self._estimate_iv_rank(chain)

        setups = []

        if direction == "bullish":
            setups.extend(self._bullish_strategies(chain, price, risk_budget, capital, confidence, target_dte, iv_rank))
        elif direction == "bearish":
            setups.extend(self._bearish_strategies(chain, price, risk_budget, capital, confidence, target_dte, iv_rank))
        elif direction == "neutral":
            setups.extend(self._neutral_strategies(chain, price, risk_budget, capital, confidence, target_dte, iv_rank))

        # Always consider cash-secured puts if bullish (get paid to wait)
        if direction == "bullish" and capital >= price * 100 * 0.1:
            csp = self._cash_secured_put(chain, price, risk_budget, capital, target_dte, iv_rank)
            if csp:
                setups.append(csp)

        # Sort by risk_reward_ratio descending, filter by affordability
        setups = [s for s in setups if s.can_trade]
        setups.sort(key=lambda s: s.risk_reward_ratio, reverse=True)

        return setups if setups else [OptionsSetup(
            strategy_name="none", description="No suitable options strategies for your account size and risk budget",
            direction=direction, can_trade=False,
            block_reason=f"Capital ${capital:.2f}, risk budget ${risk_budget:.2f} - may need more capital for options",
        )]

    # ─── Bullish Strategies ─────────────────────────────────────────

    def _bullish_strategies(self, chain, price, risk_budget, capital, confidence, target_dte, iv_rank):
        setups = []

        # Pick expiration closest to target
        calls_by_exp = self._best_expiry(chain.calls, target_dte)
        if not calls_by_exp:
            return []

        atm_strike = chain.get_atm_strike()

        # 1. Long Call (simple, high reward, costs premium)
        long_call = self._find_contract(calls_by_exp, atm_strike, offset=1)
        if long_call and long_call.mid_price > 0:
            cost = long_call.mid_price * 100
            if cost <= risk_budget * 2:  # Allow up to 2x risk budget for options
                setup = OptionsSetup(
                    strategy_name="long_call",
                    description=f"Buy {long_call.strike} Call expiring {long_call.expiration}",
                    direction="bullish",
                    contracts=[{
                        "action": "BUY",
                        "symbol": long_call.symbol,
                        "type": "call",
                        "strike": long_call.strike,
                        "expiration": long_call.expiration,
                        "price": long_call.mid_price,
                        "qty": max(1, int(risk_budget / cost)),
                        "delta": long_call.delta,
                    }],
                    max_loss=cost,
                    max_profit=cost * 5,  # Theoretical, depends on move
                    breakeven=long_call.strike + long_call.mid_price,
                    probability_of_profit=abs(long_call.delta) * 100 if long_call.delta else 40,
                    capital_required=cost,
                    risk_reward_ratio=5.0,
                    days_to_expiry=long_call.days_to_expiry,
                    iv_rank=iv_rank,
                    why=[
                        f"Bullish on {chain.underlying} at ${price:.2f}",
                        f"Max loss is ${cost:.2f} (the premium you pay)",
                        "Best when IV is low (cheap options)" if iv_rank < 40 else "IV is elevated - consider a spread instead",
                    ],
                    suggested_exit_profit_pct=75,
                    suggested_exit_loss_pct=50,
                )
                setups.append(setup)

        # 2. Bull Call Spread (defined risk, cheaper than long call)
        otm_call = self._find_contract(calls_by_exp, atm_strike, offset=3)
        if long_call and otm_call and long_call.mid_price > 0 and otm_call.mid_price > 0:
            net_debit = (long_call.mid_price - otm_call.mid_price) * 100
            max_profit = (otm_call.strike - long_call.strike) * 100 - net_debit
            if net_debit > 0 and net_debit <= risk_budget and max_profit > 0:
                setup = OptionsSetup(
                    strategy_name="bull_call_spread",
                    description=f"Buy {long_call.strike}/{otm_call.strike} Call Spread exp {long_call.expiration}",
                    direction="bullish",
                    contracts=[
                        {
                            "action": "BUY", "symbol": long_call.symbol,
                            "type": "call", "strike": long_call.strike,
                            "expiration": long_call.expiration,
                            "price": long_call.mid_price, "qty": 1,
                            "delta": long_call.delta,
                        },
                        {
                            "action": "SELL", "symbol": otm_call.symbol,
                            "type": "call", "strike": otm_call.strike,
                            "expiration": otm_call.expiration,
                            "price": otm_call.mid_price, "qty": 1,
                            "delta": otm_call.delta,
                        },
                    ],
                    max_loss=net_debit,
                    max_profit=max_profit,
                    breakeven=long_call.strike + net_debit / 100,
                    probability_of_profit=abs(long_call.delta) * 100 if long_call.delta else 45,
                    capital_required=net_debit,
                    risk_reward_ratio=round(max_profit / net_debit, 2) if net_debit > 0 else 0,
                    days_to_expiry=long_call.days_to_expiry,
                    iv_rank=iv_rank,
                    why=[
                        f"Defined risk: max loss ${net_debit:.2f}, max profit ${max_profit:.2f}",
                        "Cheaper than buying a call outright",
                        "Great when IV is high" if iv_rank > 50 else "Works in any IV environment",
                        f"Fits your risk budget of ${risk_budget:.2f}",
                    ],
                    suggested_exit_profit_pct=50,
                    suggested_exit_loss_pct=100,
                )
                setups.append(setup)

        return setups

    # ─── Bearish Strategies ─────────────────────────────────────────

    def _bearish_strategies(self, chain, price, risk_budget, capital, confidence, target_dte, iv_rank):
        setups = []

        puts_by_exp = self._best_expiry(chain.puts, target_dte)
        if not puts_by_exp:
            return []

        atm_strike = chain.get_atm_strike()

        # 1. Long Put
        long_put = self._find_contract(puts_by_exp, atm_strike, offset=-1)
        if long_put and long_put.mid_price > 0:
            cost = long_put.mid_price * 100
            if cost <= risk_budget * 2:
                setup = OptionsSetup(
                    strategy_name="long_put",
                    description=f"Buy {long_put.strike} Put expiring {long_put.expiration}",
                    direction="bearish",
                    contracts=[{
                        "action": "BUY", "symbol": long_put.symbol,
                        "type": "put", "strike": long_put.strike,
                        "expiration": long_put.expiration,
                        "price": long_put.mid_price,
                        "qty": max(1, int(risk_budget / cost)),
                        "delta": long_put.delta,
                    }],
                    max_loss=cost,
                    max_profit=long_put.strike * 100 - cost,
                    breakeven=long_put.strike - long_put.mid_price,
                    probability_of_profit=abs(long_put.delta) * 100 if long_put.delta else 40,
                    capital_required=cost,
                    risk_reward_ratio=3.0,
                    days_to_expiry=long_put.days_to_expiry,
                    iv_rank=iv_rank,
                    why=[
                        f"Bearish on {chain.underlying} at ${price:.2f}",
                        f"Max loss is ${cost:.2f} (the premium)",
                        "Profits if stock drops below breakeven",
                    ],
                    suggested_exit_profit_pct=75,
                    suggested_exit_loss_pct=50,
                )
                setups.append(setup)

        # 2. Bear Put Spread (defined risk)
        otm_put = self._find_contract(puts_by_exp, atm_strike, offset=-3)
        if long_put and otm_put and long_put.mid_price > 0 and otm_put.mid_price > 0:
            net_debit = (long_put.mid_price - otm_put.mid_price) * 100
            max_profit = (long_put.strike - otm_put.strike) * 100 - net_debit
            if net_debit > 0 and net_debit <= risk_budget and max_profit > 0:
                setup = OptionsSetup(
                    strategy_name="bear_put_spread",
                    description=f"Buy {long_put.strike}/{otm_put.strike} Put Spread exp {long_put.expiration}",
                    direction="bearish",
                    contracts=[
                        {
                            "action": "BUY", "symbol": long_put.symbol,
                            "type": "put", "strike": long_put.strike,
                            "expiration": long_put.expiration,
                            "price": long_put.mid_price, "qty": 1,
                            "delta": long_put.delta,
                        },
                        {
                            "action": "SELL", "symbol": otm_put.symbol,
                            "type": "put", "strike": otm_put.strike,
                            "expiration": otm_put.expiration,
                            "price": otm_put.mid_price, "qty": 1,
                            "delta": otm_put.delta,
                        },
                    ],
                    max_loss=net_debit,
                    max_profit=max_profit,
                    breakeven=long_put.strike - net_debit / 100,
                    capital_required=net_debit,
                    risk_reward_ratio=round(max_profit / net_debit, 2) if net_debit > 0 else 0,
                    days_to_expiry=long_put.days_to_expiry,
                    iv_rank=iv_rank,
                    why=[
                        f"Defined risk: max loss ${net_debit:.2f}, max profit ${max_profit:.2f}",
                        "Cheaper than buying a put outright",
                        f"Fits your risk budget of ${risk_budget:.2f}",
                    ],
                )
                setups.append(setup)

        return setups

    # ─── Neutral / Income Strategies ────────────────────────────────

    def _neutral_strategies(self, chain, price, risk_budget, capital, confidence, target_dte, iv_rank):
        setups = []
        atm_strike = chain.get_atm_strike()

        calls_by_exp = self._best_expiry(chain.calls, target_dte)
        puts_by_exp = self._best_expiry(chain.puts, target_dte)

        if not calls_by_exp or not puts_by_exp:
            return []

        # Iron Condor (sell OTM put spread + sell OTM call spread)
        sell_put = self._find_contract(puts_by_exp, atm_strike, offset=-2)
        buy_put = self._find_contract(puts_by_exp, atm_strike, offset=-4)
        sell_call = self._find_contract(calls_by_exp, atm_strike, offset=2)
        buy_call = self._find_contract(calls_by_exp, atm_strike, offset=4)

        if all([sell_put, buy_put, sell_call, buy_call]):
            sp, bp, sc, bc = sell_put, buy_put, sell_call, buy_call
            if sp.mid_price > 0 and sc.mid_price > 0 and bp.mid_price >= 0 and bc.mid_price >= 0:
                credit = ((sp.mid_price - bp.mid_price) + (sc.mid_price - bc.mid_price)) * 100
                put_width = (sp.strike - bp.strike) * 100
                call_width = (bc.strike - sc.strike) * 100
                max_loss = max(put_width, call_width) - credit

                if credit > 0 and max_loss > 0 and max_loss <= risk_budget * 2:
                    setup = OptionsSetup(
                        strategy_name="iron_condor",
                        description=f"Iron Condor: {bp.strike}/{sp.strike} puts, {sc.strike}/{bc.strike} calls exp {sp.expiration}",
                        direction="neutral",
                        contracts=[
                            {"action": "SELL", "symbol": sp.symbol, "type": "put", "strike": sp.strike, "expiration": sp.expiration, "price": sp.mid_price, "qty": 1, "delta": sp.delta},
                            {"action": "BUY", "symbol": bp.symbol, "type": "put", "strike": bp.strike, "expiration": bp.expiration, "price": bp.mid_price, "qty": 1, "delta": bp.delta},
                            {"action": "SELL", "symbol": sc.symbol, "type": "call", "strike": sc.strike, "expiration": sc.expiration, "price": sc.mid_price, "qty": 1, "delta": sc.delta},
                            {"action": "BUY", "symbol": bc.symbol, "type": "call", "strike": bc.strike, "expiration": bc.expiration, "price": bc.mid_price, "qty": 1, "delta": bc.delta},
                        ],
                        max_profit=credit,
                        max_loss=max_loss,
                        breakeven=0,  # Two breakeven points
                        probability_of_profit=65,  # Typical IC
                        capital_required=max_loss,
                        risk_reward_ratio=round(credit / max_loss, 2) if max_loss > 0 else 0,
                        days_to_expiry=sp.days_to_expiry,
                        iv_rank=iv_rank,
                        why=[
                            f"Collect ${credit:.2f} premium if {chain.underlying} stays between ${sp.strike} and ${sc.strike}",
                            f"Max loss ${max_loss:.2f} if stock moves past either wing",
                            "Best strategy when IV is high" if iv_rank > 50 else "Consider waiting for higher IV",
                            "Profits from time decay (theta)",
                        ],
                        suggested_exit_profit_pct=50,
                        suggested_exit_loss_pct=200,
                    )
                    setups.append(setup)

        # Straddle (buy ATM call + ATM put, play big moves)
        atm_call = self._find_contract(calls_by_exp, atm_strike, offset=0)
        atm_put = self._find_contract(puts_by_exp, atm_strike, offset=0)

        if atm_call and atm_put and atm_call.mid_price > 0 and atm_put.mid_price > 0:
            cost = (atm_call.mid_price + atm_put.mid_price) * 100
            if cost <= risk_budget * 2:
                setup = OptionsSetup(
                    strategy_name="long_straddle",
                    description=f"Buy {atm_strike} Straddle (Call + Put) exp {atm_call.expiration}",
                    direction="neutral",
                    contracts=[
                        {"action": "BUY", "symbol": atm_call.symbol, "type": "call", "strike": atm_strike, "expiration": atm_call.expiration, "price": atm_call.mid_price, "qty": 1, "delta": atm_call.delta},
                        {"action": "BUY", "symbol": atm_put.symbol, "type": "put", "strike": atm_strike, "expiration": atm_put.expiration, "price": atm_put.mid_price, "qty": 1, "delta": atm_put.delta},
                    ],
                    max_loss=cost,
                    max_profit=cost * 5,
                    breakeven=atm_strike,  # Simplified
                    probability_of_profit=35,  # Need big move
                    capital_required=cost,
                    risk_reward_ratio=5.0,
                    days_to_expiry=atm_call.days_to_expiry,
                    iv_rank=iv_rank,
                    why=[
                        "Profits from a big move in EITHER direction",
                        f"Need {chain.underlying} to move more than ${(atm_call.mid_price + atm_put.mid_price):.2f} from ${atm_strike}",
                        "Best before earnings or big catalysts",
                        "Best when IV is LOW (cheap)" if iv_rank < 30 else "IV is high - straddle is expensive",
                    ],
                    suggested_exit_profit_pct=50,
                    suggested_exit_loss_pct=50,
                )
                setups.append(setup)

        return setups

    # ─── Cash Secured Put ───────────────────────────────────────────

    def _cash_secured_put(self, chain, price, risk_budget, capital, target_dte, iv_rank):
        """Sell a put to get paid while waiting for a lower entry."""
        puts_by_exp = self._best_expiry(chain.puts, target_dte)
        if not puts_by_exp:
            return None

        atm_strike = chain.get_atm_strike()
        otm_put = self._find_contract(puts_by_exp, atm_strike, offset=-2)

        if not otm_put or otm_put.mid_price <= 0:
            return None

        collateral = otm_put.strike * 100
        if collateral > capital:
            return None

        credit = otm_put.mid_price * 100
        annual_return = (credit / collateral) * (365 / max(1, otm_put.days_to_expiry)) * 100

        return OptionsSetup(
            strategy_name="cash_secured_put",
            description=f"Sell {otm_put.strike} Put exp {otm_put.expiration} for ${credit:.2f} credit",
            direction="bullish",
            contracts=[{
                "action": "SELL", "symbol": otm_put.symbol,
                "type": "put", "strike": otm_put.strike,
                "expiration": otm_put.expiration,
                "price": otm_put.mid_price, "qty": 1,
                "delta": otm_put.delta,
            }],
            max_profit=credit,
            max_loss=collateral - credit,
            breakeven=otm_put.strike - otm_put.mid_price,
            probability_of_profit=100 - abs(otm_put.delta or 0.3) * 100,
            capital_required=collateral,
            risk_reward_ratio=round(credit / (collateral - credit), 4) if collateral > credit else 0,
            days_to_expiry=otm_put.days_to_expiry,
            iv_rank=iv_rank,
            why=[
                f"Get paid ${credit:.2f} to wait for {chain.underlying} at ${otm_put.strike}",
                f"If assigned, your cost basis is ${otm_put.strike - otm_put.mid_price:.2f}",
                f"Annualized return: {annual_return:.1f}%",
                f"Requires ${collateral:.2f} collateral",
                "Great when IV is high (more premium)" if iv_rank > 40 else "Lower premium in low IV",
            ],
            suggested_exit_profit_pct=50,
            suggested_exit_loss_pct=200,
        )

    # ─── Helpers ────────────────────────────────────────────────────

    def _best_expiry(self, contracts: list, target_dte: int) -> list:
        """Find contracts closest to the target DTE."""
        if not contracts:
            return []

        expirations = sorted(set(c.expiration for c in contracts))
        if not expirations:
            return []

        target_date = datetime.now() + timedelta(days=target_dte)
        best_exp = min(expirations, key=lambda e: abs(
            (datetime.strptime(e, "%Y-%m-%d") - target_date).days
        ) if e else 999)

        return [c for c in contracts if c.expiration == best_exp]

    def _find_contract(self, contracts: list, atm_strike: float, offset: int = 0) -> OptionContract | None:
        """
        Find a contract near ATM with offset.
        offset=0: ATM, offset=1: 1 strike OTM for calls, offset=-1: 1 strike OTM for puts
        """
        if not contracts:
            return None

        strikes = sorted(set(c.strike for c in contracts))
        if not strikes:
            return None

        # Find the ATM index
        atm_idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - atm_strike))
        target_idx = atm_idx + offset

        if target_idx < 0 or target_idx >= len(strikes):
            target_idx = max(0, min(len(strikes) - 1, target_idx))

        target_strike = strikes[target_idx]
        matches = [c for c in contracts if c.strike == target_strike]
        return matches[0] if matches else None

    def _estimate_iv_rank(self, chain: OptionsChain) -> float:
        """
        Estimate IV rank from current chain data.
        Simple heuristic: compare ATM IV to typical range.
        A proper implementation would use historical IV data.
        """
        atm_strike = chain.get_atm_strike()
        atm_contracts = [c for c in chain.calls + chain.puts
                         if c.strike == atm_strike and c.implied_volatility > 0]

        if not atm_contracts:
            return 50.0  # Default to middle

        avg_iv = sum(c.implied_volatility for c in atm_contracts) / len(atm_contracts)

        # Rough heuristic: typical stock IV is 15-60%
        # Map to 0-100 rank
        iv_rank = min(100, max(0, (avg_iv - 0.15) / 0.45 * 100))
        return round(iv_rank, 1)

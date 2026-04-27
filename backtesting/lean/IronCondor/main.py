# region imports
from AlgorithmImports import *
# endregion


class IronCondor(QCAlgorithm):
    """
    Iron condor on SPY:
    - Entry: monthly, sell 16-delta call + put spread (5-point wings), 45 DTE
    - Exit: 50% profit OR 200% loss OR 21 DTE remaining
    - Position size: 5% of portfolio per condor (defined-risk)
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 1, 1)
        self.set_cash(100_000)

        equity = self.add_equity("SPY", Resolution.MINUTE)
        self.spy = equity.symbol

        option = self.add_option("SPY", Resolution.MINUTE)
        option.set_filter(lambda u: u.include_weeklys()
                                     .expiration(30, 60)
                                     .delta(0.05, 0.35))

        self.option_symbol = option.symbol
        self.last_entry_month = -1
        self.active_condor = None

    def on_data(self, data: Slice):
        chain = data.option_chains.get(self.option_symbol)
        if not chain:
            return

        # Check exit conditions on active condor
        if self.active_condor:
            self._check_exit(chain)
            return

        # Enter once per month
        month = self.time.month
        if month == self.last_entry_month:
            return

        self._enter_condor(chain)

    def _enter_condor(self, chain):
        contracts = list(chain)
        if not contracts:
            return

        # Find expiry ~45 DTE
        target_expiry = self.time + timedelta(days=45)
        expiries = sorted(set(c.expiry for c in contracts),
                          key=lambda e: abs((e - target_expiry).days))
        if not expiries:
            return
        expiry = expiries[0]

        calls = [c for c in contracts
                 if c.right == OptionRight.CALL and c.expiry == expiry
                 and c.greeks is not None]
        puts  = [c for c in contracts
                 if c.right == OptionRight.PUT  and c.expiry == expiry
                 and c.greeks is not None]

        if not calls or not puts:
            return

        # Short strikes: closest to 16-delta
        short_call = min(calls, key=lambda c: abs(abs(c.greeks.delta) - 0.16))
        short_put  = min(puts,  key=lambda c: abs(abs(c.greeks.delta) - 0.16))

        # Long strikes: 5 points OTM from shorts
        long_call_strike = short_call.strike + 5
        long_put_strike  = short_put.strike  - 5

        long_call = min(
            (c for c in calls if abs(c.strike - long_call_strike) < 2.5),
            key=lambda c: abs(c.strike - long_call_strike), default=None)
        long_put = min(
            (c for c in puts if abs(c.strike - long_put_strike) < 2.5),
            key=lambda c: abs(c.strike - long_put_strike), default=None)

        if not long_call or not long_put:
            return

        # Approximate net credit from mid prices
        net_credit_approx = (
            (short_call.bid_price + short_call.ask_price) / 2
            + (short_put.bid_price  + short_put.ask_price)  / 2
            - (long_call.bid_price  + long_call.ask_price)  / 2
            - (long_put.bid_price   + long_put.ask_price)   / 2
        )
        wing_width = 5.0
        max_risk_per_contract = (wing_width - net_credit_approx) * 100
        if max_risk_per_contract <= 0:
            return

        # Size: 5% max risk per condor
        budget = self.portfolio.total_portfolio_value * 0.05
        quantity = max(1, int(budget / max_risk_per_contract))

        self.market_order(short_call.symbol, -quantity)
        self.market_order(long_call.symbol,   quantity)
        self.market_order(short_put.symbol,  -quantity)
        self.market_order(long_put.symbol,    quantity)

        entry_credit = net_credit_approx * quantity * 100
        self.active_condor = {
            "short_call":   short_call.symbol,
            "long_call":    long_call.symbol,
            "short_put":    short_put.symbol,
            "long_put":     long_put.symbol,
            "quantity":     quantity,
            "entry_credit": entry_credit,
            "expiry":       expiry,
        }
        self.last_entry_month = self.time.month
        self.log(f"ENTER condor exp={expiry.date()} qty={quantity} "
                 f"SC={short_call.strike} SP={short_put.strike} "
                 f"credit=${entry_credit:.0f}")

    def _check_exit(self, chain):
        c = self.active_condor
        dte = (c["expiry"] - self.time).days

        def mid(sym):
            contract = next((x for x in chain if x.symbol == sym), None)
            if contract is None:
                return 0.0
            return (contract.bid_price + contract.ask_price) / 2

        current_value = (
            -mid(c["short_call"]) - mid(c["short_put"])
            + mid(c["long_call"])  + mid(c["long_put"])
        ) * c["quantity"] * 100

        pnl = c["entry_credit"] + current_value  # positive = profit
        max_profit = c["entry_credit"]

        exit_reason = None
        if max_profit > 0 and pnl >= 0.50 * max_profit:
            exit_reason = "50pct_profit"
        elif max_profit > 0 and pnl <= -2.0 * max_profit:
            exit_reason = "2x_loss"
        elif dte <= 21:
            exit_reason = "21dte"

        if exit_reason:
            self.market_order(c["short_call"],  c["quantity"])
            self.market_order(c["long_call"],   -c["quantity"])
            self.market_order(c["short_put"],   c["quantity"])
            self.market_order(c["long_put"],    -c["quantity"])
            self.log(f"EXIT condor reason={exit_reason} pnl=${pnl:.0f}")
            self.active_condor = None

from AlgorithmImports import *

class BuyHoldSPY(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2019, 1, 1)
        self.set_end_date(2021, 1, 1)
        self.set_cash(100_000)
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol

    def on_data(self, data):
        if not self.portfolio.invested:
            self.set_holdings(self.spy, 1.0)

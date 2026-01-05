class TradingContext:
    def __init__(self):
        self.active_trades = {}
        self.state = "SCANNING" # SCANNING, ENTERING, EXITING, WAITING
        self.last_update = None
        
    def update_state(self, new_state):
        self.state = new_state
        print(f"State changed to: {self.state}")

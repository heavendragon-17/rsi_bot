import pandas_ta as ta

class Indicators:
    @staticmethod
    def calculate_rsi(series, length=14):
        return ta.rsi(series, length=length)

    @staticmethod
    def calculate_wma(series, length=9):
        return ta.wma(series, length=length)

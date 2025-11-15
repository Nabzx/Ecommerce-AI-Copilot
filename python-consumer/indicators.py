"""
Technical Indicators Module
Calculates RSI, MACD, Bollinger Bands, and Volatility incrementally
"""

from collections import deque
from typing import Optional, Tuple
import math


class TechnicalIndicators:
    """Incremental technical indicator calculator"""
    
    def __init__(self):
        # Price history for calculations
        self.price_history = deque(maxlen=200)  # Store last 200 prices
        self.gain_history = deque(maxlen=14)  # For RSI
        self.loss_history = deque(maxlen=14)  # For RSI
        
        # MACD state
        self.ema_12 = None
        self.ema_26 = None
        self.macd_line = None
        self.signal_line = None
        self.signal_ema = None  # EMA of MACD line for signal
        
        # Bollinger Bands state
        self.sma_20 = None
        self.sma_20_history = deque(maxlen=20)
        
    def update_price(self, price: float) -> None:
        """Add new price to history"""
        if len(self.price_history) > 0:
            prev_price = self.price_history[-1]
            change = price - prev_price
            
            # Update RSI gain/loss
            if change > 0:
                self.gain_history.append(change)
                self.loss_history.append(0.0)
            else:
                self.gain_history.append(0.0)
                self.loss_history.append(abs(change))
        
        self.price_history.append(price)
    
    def calculate_rsi(self, period: int = 14) -> Optional[float]:
        """
        Calculate Relative Strength Index (RSI)
        RSI = 100 - (100 / (1 + RS))
        RS = Average Gain / Average Loss
        """
        if len(self.gain_history) < period:
            return None
        
        avg_gain = sum(self.gain_history) / len(self.gain_history)
        avg_loss = sum(self.loss_history) / len(self.loss_history)
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return round(rsi, 2)
    
    def calculate_macd(self, fast: int = 12, slow: int = 26, signal: int = 9) -> Optional[Tuple[float, float, float]]:
        """
        Calculate MACD (Moving Average Convergence Divergence)
        Returns: (macd_line, signal_line, histogram)
        """
        if len(self.price_history) < slow:
            return None
        
        # Calculate EMAs
        prices = list(self.price_history)
        
        # Fast EMA (12)
        if self.ema_12 is None:
            self.ema_12 = sum(prices[-fast:]) / fast
        else:
            multiplier = 2 / (fast + 1)
            self.ema_12 = (prices[-1] - self.ema_12) * multiplier + self.ema_12
        
        # Slow EMA (26)
        if self.ema_26 is None:
            self.ema_26 = sum(prices[-slow:]) / slow
        else:
            multiplier = 2 / (slow + 1)
            self.ema_26 = (prices[-1] - self.ema_26) * multiplier + self.ema_26
        
        # MACD Line
        self.macd_line = self.ema_12 - self.ema_26
        
        # Signal Line (EMA of MACD)
        if self.signal_ema is None:
            self.signal_ema = self.macd_line
        else:
            multiplier = 2 / (signal + 1)
            self.signal_ema = (self.macd_line - self.signal_ema) * multiplier + self.signal_ema
        
        self.signal_line = self.signal_ema
        
        # Histogram
        histogram = self.macd_line - self.signal_line
        
        return (
            round(self.macd_line, 4),
            round(self.signal_line, 4),
            round(histogram, 4)
        )
    
    def calculate_bollinger_bands(self, period: int = 20, std_dev: float = 2.0) -> Optional[Tuple[float, float, float]]:
        """
        Calculate Bollinger Bands
        Returns: (upper_band, middle_band, lower_band)
        """
        if len(self.price_history) < period:
            return None
        
        prices = list(self.price_history)[-period:]
        
        # Middle band (SMA)
        sma = sum(prices) / len(prices)
        self.sma_20 = sma
        
        # Standard deviation
        variance = sum((p - sma) ** 2 for p in prices) / len(prices)
        std = math.sqrt(variance)
        
        # Upper and lower bands
        upper = sma + (std_dev * std)
        lower = sma - (std_dev * std)
        
        return (
            round(upper, 2),
            round(sma, 2),
            round(lower, 2)
        )
    
    def calculate_volatility(self, period: int = 20) -> Optional[float]:
        """
        Calculate Volatility (Standard Deviation)
        """
        if len(self.price_history) < period:
            return None
        
        prices = list(self.price_history)[-period:]
        mean = sum(prices) / len(prices)
        
        variance = sum((p - mean) ** 2 for p in prices) / len(prices)
        std = math.sqrt(variance)
        
        return round(std, 2)
    
    def get_all_indicators(self) -> dict:
        """Calculate all indicators and return as dictionary"""
        indicators = {}
        
        # RSI
        rsi = self.calculate_rsi(14)
        if rsi is not None:
            indicators['rsi'] = rsi
        
        # MACD
        macd_result = self.calculate_macd(12, 26, 9)
        if macd_result is not None:
            indicators['macd'] = macd_result[0]
            indicators['macd_signal'] = macd_result[1]
            indicators['macd_hist'] = macd_result[2]
        
        # Bollinger Bands
        bb_result = self.calculate_bollinger_bands(20, 2.0)
        if bb_result is not None:
            indicators['bb_upper'] = bb_result[0]
            indicators['bb_middle'] = bb_result[1]
            indicators['bb_lower'] = bb_result[2]
        
        # Volatility
        volatility = self.calculate_volatility(20)
        if volatility is not None:
            indicators['volatility'] = volatility
        
        return indicators


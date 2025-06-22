import logging
from datetime import timedelta
import numpy as np

def format_time(seconds):
    """Formats seconds into a human-readable string like '3d 4h 5m'."""
    if not isinstance(seconds, (int, float)) or seconds < 0:
        return "N/A"
    delta = timedelta(seconds=seconds)
    days, remainder = divmod(delta.total_seconds(), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    
    parts = []
    if days > 0:
        parts.append(f"{int(days)}d")
    if hours > 0:
        parts.append(f"{int(hours)}h")
    if minutes > 0 or not parts: # Show minutes if it's the only unit
        parts.append(f"{int(minutes)}m")
        
    return " ".join(parts) if parts else "0m"

def get_trend_indicator(price_history):
    """
    Analyzes price history to determine a simple trend indicator.
    Returns '↑' for upward, '↓' for downward, and '↔' for stable.
    """
    if not price_history or len(price_history) < 2:
        return '?' # Not enough data

    try:
        prices = [item['average'] for item in price_history]
        
        # Split data into first and second half
        half_point = len(prices) // 2
        first_half_avg = np.mean(prices[:half_point])
        second_half_avg = np.mean(prices[half_point:])
        
        # Calculate percentage change
        if first_half_avg == 0:
            return '?'
        change = ((second_half_avg - first_half_avg) / first_half_avg) * 100
        
        if change > 5: # More than 5% increase
            return '↑'  # Upward
        elif change < -5: # More than 5% decrease
            return '↓'  # Downward
        else:
            return '↔'  # Stable
    except (TypeError, KeyError, IndexError) as e:
        logging.warning(f"Could not calculate trend indicator due to data issue: {e}")
        return '?'


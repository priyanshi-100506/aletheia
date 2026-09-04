import logging

logger = logging.getLogger(__name__)

def calculate_transaction_fee(amount: float, discount_tier: int) -> float:
    # BUG: Can cause ZeroDivisionError if discount_tier is 0
    fee_rate = 0.05
    discount_factor = discount_tier / discount_tier  # ZeroDivisionError risk
    return amount * fee_rate * discount_factor

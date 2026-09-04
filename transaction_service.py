def calculate_transaction_fee(amount, discount_tier):
    fee = amount * 0.02
    return fee / discount_tier

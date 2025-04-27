import logging
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP # Import rounding mode
import datetime as dt
from typing import List, Dict, Tuple, Optional

# Import the Transaction class definition from parser
try:
    from parser import Transaction
except ImportError:
    logging.warning("Could not import Transaction from parser. Assuming basic structure.")
    class Transaction: # Minimal definition
        def __init__(self, date, description, amount, category="Uncategorized", transaction_type=None, id=None, **kwargs):
            self.id = id; self.date = date; self.description = description
            self.amount = Decimal(amount); self.category = category if category else "Uncategorized"
            self.transaction_type = transaction_type

# Define categories that represent transfers or internal payments (lowercase)
TRANSFER_CATEGORIES = {"transfers", "payments"}
# Define categories typically associated with income (lowercase)
INCOME_CATEGORIES = {"income"}


def _validate_transactions(transactions: List[Transaction]) -> List[Transaction]:
    """Helper to ensure transactions have Decimal amounts."""
    valid_transactions = []
    for tx in transactions:
        if not isinstance(tx.amount, Decimal):
            try:
                tx.amount = Decimal(tx.amount)
                valid_transactions.append(tx)
            except Exception as e:
                 logging.warning(f"Skipping transaction during validation due to amount conversion error: {tx} | Error: {e}")
        else:
            valid_transactions.append(tx)
    return valid_transactions

def calculate_summary_insights(transactions: List[Transaction]) -> Dict[str, any]:
    """
    Calculates more nuanced financial insights from a list of transactions.
    """
    valid_transactions = _validate_transactions(transactions)

    operational_income = Decimal('0.00')
    operational_spending = Decimal('0.00')
    transfers_in = Decimal('0.00')
    transfers_out = Decimal('0.00')
    spending_by_category: Dict[str, Decimal] = defaultdict(Decimal)
    income_by_category: Dict[str, Decimal] = defaultdict(Decimal)
    refunds_by_category: Dict[str, Decimal] = defaultdict(Decimal)

    for tx in valid_transactions:
        category_lower = tx.category.lower()
        amount = tx.amount
        is_transfer_or_payment = category_lower in TRANSFER_CATEGORIES
        is_income_category = category_lower in INCOME_CATEGORIES
        is_likely_refund = amount > 0 and not is_income_category and not is_transfer_or_payment

        if amount > 0: # Money In
            income_by_category[tx.category] += amount
            if is_transfer_or_payment: transfers_in += amount
            elif is_income_category: operational_income += amount
            elif is_likely_refund: refunds_by_category[tx.category] += amount
            else: operational_income += amount
        elif amount < 0: # Money Out
            abs_amount = abs(amount)
            spending_by_category[tx.category] += abs_amount
            if is_transfer_or_payment: transfers_out += abs_amount
            else: operational_spending += abs_amount

    net_spending_by_category: Dict[str, Decimal] = defaultdict(Decimal)
    for category, spent in spending_by_category.items():
        refunded = refunds_by_category.get(category, Decimal('0.00'))
        net_spending_by_category[category] = max(Decimal('0.00'), spent - refunded)

    net_operational_flow = operational_income - operational_spending
    net_transfer_flow = transfers_in - transfers_out

    def capitalize_dict_keys(d: Dict[str, Decimal]) -> Dict[str, Decimal]:
        return {k.title(): v for k, v in d.items()}

    summary = {
        "operational_income": operational_income, "operational_spending": operational_spending,
        "net_operational_flow": net_operational_flow, "transfers_in": transfers_in,
        "transfers_out": transfers_out, "net_transfer_flow": net_transfer_flow,
        "spending_by_category": capitalize_dict_keys(spending_by_category),
        "income_by_category": capitalize_dict_keys(income_by_category),
        "refunds_by_category": capitalize_dict_keys(refunds_by_category),
        "net_spending_by_category": capitalize_dict_keys(net_spending_by_category),
        "net_total_flow_all": net_operational_flow + net_transfer_flow,
        "transaction_count": len(valid_transactions)
    }
    return summary

# --- Change: Add Monthly Trends Calculation ---
def calculate_monthly_trends(transactions: List[Transaction]) -> Dict[str, any]:
    """
    Calculates month-over-month spending trends by category.

    Args:
        transactions: A list of Transaction objects.

    Returns:
        A dictionary containing trend analysis:
        {
            "current_month": "YYYY-MM",
            "previous_month": "YYYY-MM",
            "trends": [
                {
                    "category": "Category Name",
                    "current_month_spending": Decimal,
                    "previous_month_spending": Decimal,
                    "change_amount": Decimal,
                    "change_percent": float | None # Percentage change or None if previous was 0
                },
                ...
            ]
        }
        Returns an error message if less than two months of data are available.
    """
    valid_transactions = _validate_transactions(transactions)
    if not valid_transactions:
        return {"error": "No valid transactions provided."}

    # Aggregate net spending (spending - refunds) by year, month, and category
    # monthly_net_spending[("YYYY-MM", "Category Title Case")] = Decimal(...)
    monthly_net_spending: Dict[Tuple[str, str], Decimal] = defaultdict(Decimal)

    for tx in valid_transactions:
        # Consider only operational spending (negative amounts, not transfers/payments)
        # and refunds (positive amounts, not income/transfers)
        category_lower = tx.category.lower()
        amount = tx.amount
        is_transfer_or_payment = category_lower in TRANSFER_CATEGORIES
        is_income_category = category_lower in INCOME_CATEGORIES

        if amount < 0 and not is_transfer_or_payment: # Operational spending
            month_key = tx.date.strftime("%Y-%m")
            # Use title case for category key in results
            category_key = tx.category.title() if tx.category else "Uncategorized"
            monthly_net_spending[(month_key, category_key)] += abs(amount)
        elif amount > 0 and not is_income_category and not is_transfer_or_payment: # Likely refund
            month_key = tx.date.strftime("%Y-%m")
            category_key = tx.category.title() if tx.category else "Uncategorized"
            # Subtract refund amount from spending for that month/category
            monthly_net_spending[(month_key, category_key)] -= amount


    # Find available months
    available_months = sorted(list(set(key[0] for key in monthly_net_spending.keys())))

    if len(available_months) < 2:
        return {"error": "Insufficient data: Less than two months of spending data available to calculate trends."}

    # Get the most recent two months
    current_month_str = available_months[-1]
    previous_month_str = available_months[-2]

    # Get all unique categories across both months
    all_categories = sorted(list(set(key[1] for key in monthly_net_spending.keys() if key[0] in [current_month_str, previous_month_str])))

    trends = []
    quantize_decimal = Decimal("0.01") # For rounding currency

    for category in all_categories:
        current_spending = monthly_net_spending.get((current_month_str, category), Decimal('0.00'))
        previous_spending = monthly_net_spending.get((previous_month_str, category), Decimal('0.00'))

        # Ensure net spending isn't negative after subtracting refunds
        current_spending = max(Decimal('0.00'), current_spending)
        previous_spending = max(Decimal('0.00'), previous_spending)

        # Round final values for consistency
        current_spending = current_spending.quantize(quantize_decimal, rounding=ROUND_HALF_UP)
        previous_spending = previous_spending.quantize(quantize_decimal, rounding=ROUND_HALF_UP)

        # Calculate change only if there was spending in either month
        if current_spending > 0 or previous_spending > 0:
            change_amount = current_spending - previous_spending
            change_percent = None
            if previous_spending > 0:
                # Calculate percentage change, round to 1 decimal place
                change_percent = float(round((change_amount / previous_spending) * 100, 1))
            elif current_spending > 0:
                 # Handle case where previous spending was 0 but current is positive (infinite increase)
                 change_percent = float('inf') # Or could return None or a large number like 9999

            trends.append({
                "category": category, # Already title case
                "current_month_spending": current_spending,
                "previous_month_spending": previous_spending,
                "change_amount": change_amount,
                "change_percent": change_percent
            })

    # Sort trends, e.g., by largest percentage increase or decrease, or alphabetically
    # Sorting by absolute percentage change descending (ignoring infinite)
    trends.sort(key=lambda x: abs(x['change_percent'] if x['change_percent'] != float('inf') else 0), reverse=True)

    return {
        "current_month": current_month_str,
        "previous_month": previous_month_str,
        "trends": trends
    }


# --- Example Usage (for testing) ---
if __name__ == '__main__':
    # ... (dummy data and summary calculation from previous version) ...
    import datetime as dt
    from decimal import Decimal

    if 'Transaction' not in globals():
        class Transaction:
            def __init__(self, date, description, amount, category="Uncategorized", transaction_type=None, id=None, **kwargs):
                self.id = id; self.date = date; self.description = description
                self.amount = Decimal(amount); self.category = category if category else "Uncategorized"
                self.transaction_type = transaction_type

    # More dummy data covering multiple months
    dummy_transactions = [
        # March Data
        Transaction(id=1, date=dt.date(2024, 3, 5), description="Grocery Store", amount=Decimal("-50.00"), category="Groceries"),
        Transaction(id=2, date=dt.date(2024, 3, 10), description="Restaurant A", amount=Decimal("-40.00"), category="Food"),
        Transaction(id=3, date=dt.date(2024, 3, 15), description="Gas", amount=Decimal("-30.00"), category="Gas"),
        Transaction(id=4, date=dt.date(2024, 3, 20), description="Paycheck", amount=Decimal("2000.00"), category="Income"),
        Transaction(id=5, date=dt.date(2024, 3, 25), description="Shopping", amount=Decimal("-100.00"), category="Shopping"),
        Transaction(id=11, date=dt.date(2024, 3, 28), description="Refund", amount=Decimal("10.00"), category="Shopping"), # March Refund

        # April Data
        Transaction(id=6, date=dt.date(2024, 4, 5), description="Grocery Store", amount=Decimal("-60.00"), category="Groceries"), # Increased
        Transaction(id=7, date=dt.date(2024, 4, 10), description="Restaurant A", amount=Decimal("-35.00"), category="Food"), # Decreased
        Transaction(id=8, date=dt.date(2024, 4, 15), description="Gas", amount=Decimal("-30.00"), category="Gas"), # Same
        Transaction(id=9, date=dt.date(2024, 4, 20), description="Paycheck", amount=Decimal("2000.00"), category="Income"),
        Transaction(id=10, date=dt.date(2024, 4, 25), description="New Subscription", amount=Decimal("-15.00"), category="Subscriptions"), # New category
        Transaction(id=12, date=dt.date(2024, 4, 26), description="Transfer Out", amount=Decimal("-500.00"), category="Transfers"), # Excluded
        Transaction(id=13, date=dt.date(2024, 4, 27), description="Payment In", amount=Decimal("100.00"), category="Payments"), # Excluded
    ]

    print("\n--- Calculating Summary (for context) ---")
    summary = calculate_summary_insights(dummy_transactions)
    import json
    print(json.dumps(summary, indent=2, default=str))


    print("\n--- Calculating Monthly Trends ---")
    trends_data = calculate_monthly_trends(dummy_transactions)
    print(json.dumps(trends_data, indent=2, default=str)) # Use default=str for Decimal

    print("\n--- Calculating Trends with Insufficient Data ---")
    insufficient_data = [
         Transaction(id=1, date=dt.date(2024, 3, 5), description="Grocery Store", amount=Decimal("-50.00"), category="Groceries"),
    ]
    trends_insufficient = calculate_monthly_trends(insufficient_data)
    print(json.dumps(trends_insufficient, indent=2, default=str))

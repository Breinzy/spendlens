# insights.py

import logging
from collections import defaultdict, Counter
import datetime as dt
from dateutil.relativedelta import relativedelta
from decimal import Decimal, InvalidOperation
from typing import List, Dict, Any, Optional

# Configure logging
log = logging.getLogger('insights')
log.setLevel(logging.INFO)
if not log.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s:%(funcName)s] - %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)

# --- Import Transaction Class Safely ---
# Attempt to import the real Transaction class.
# This should now point to database_supabase.Transaction after refactoring.
try:
    from database_supabase import Transaction  # Ensure this matches your refactored DB module name

    log.info("Successfully imported Transaction class from database_supabase module.")
except ImportError:
    try:
        # Fallback for older structure or direct testing if database_supabase isn't in path
        from database import Transaction  # type: ignore

        log.warning("Imported Transaction class from older 'database' module as fallback.")
    except ImportError:
        log.error("Could not import Transaction class. Defining a basic placeholder for insights.py.")


        # Define a placeholder class with expected attributes if import fails
        class Transaction:  # type: ignore
            def __init__(self, id: Optional[int], user_id: str, date: Optional[dt.date],
                         description: Optional[str], amount: Optional[Decimal], category: Optional[str],
                         transaction_type: Optional[str] = None, source_account_type: Optional[str] = None,
                         source_filename: Optional[str] = None, raw_description: Optional[str] = None,
                         client_name: Optional[str] = None, invoice_id: Optional[str] = None,
                         project_id: Optional[str] = None, payout_source: Optional[str] = None,
                         transaction_origin: Optional[str] = None,
                         created_at: Optional[dt.datetime] = None,
                         updated_at: Optional[dt.datetime] = None):
                self.id = id
                self.user_id = user_id
                self.date = date
                self.description = description
                self.amount = amount
                self.category = category
                self.transaction_type = transaction_type
                # Add other attributes as needed by insights functions
                self.raw_description = raw_description if raw_description else description

            def to_dict(self) -> Dict[str, Any]:  # Add a basic to_dict for testing if needed
                return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}


# --- Helper Function ---
def get_month_year_str(date_obj: Optional[dt.date]) -> Optional[str]:
    """Formats a date object into 'YYYY-MM' string, or returns None if date_obj is None."""
    if date_obj is None:
        return None
    return date_obj.strftime('%Y-%m')


# --- Summary Statistics ---
def calculate_summary_insights(transactions: List[Transaction]) -> Dict[str, Any]:
    log.info(f"Calculating summary insights for {len(transactions)} transactions.")
    summary = {
        "total_transactions": 0,  # Initialize to 0
        "period_start_date": None, "period_end_date": None,
        "total_income": "0.00", "total_spending": "0.00",
        "total_payments_transfers": "0.00", "net_flow_operational": "0.00",
        "net_change_total": "0.00",
        "spending_by_category": {}, "income_by_category": {},
        "average_transaction_amount": "0.00", "median_transaction_amount": "0.00",
    }

    if not transactions:
        log.warning("No transactions provided for summary calculation.")
        return summary

    valid_transactions = [tx for tx in transactions if tx.date is not None and tx.amount is not None]
    if not valid_transactions:
        log.warning("No transactions with valid dates and amounts for summary.")
        summary["total_transactions"] = len(transactions)  # Still report total attempted
        return summary

    summary["total_transactions"] = len(valid_transactions)  # Count only valid ones for calculations
    valid_transactions.sort(key=lambda t: t.date)  # type: ignore
    summary["period_start_date"] = valid_transactions[0].date.isoformat() if valid_transactions[
        0].date else None  # type: ignore
    summary["period_end_date"] = valid_transactions[-1].date.isoformat() if valid_transactions[
        -1].date else None  # type: ignore

    total_income_dec = Decimal('0')
    total_spending_dec = Decimal('0')
    total_payments_transfers_dec = Decimal('0')
    net_change_total_dec = Decimal('0')
    spending_by_category_dec = defaultdict(Decimal)
    income_by_category_dec = defaultdict(Decimal)
    all_amounts_dec = []

    operational_categories_to_exclude = ['Payments', 'Transfers', 'Ignore', 'Internal Transfer']  # Case-sensitive

    for tx in valid_transactions:
        amount_dec = tx.amount  # Should already be Decimal
        net_change_total_dec += amount_dec
        all_amounts_dec.append(amount_dec)
        category = tx.category if tx.category else 'Uncategorized'

        is_operational_exclusion = category in operational_categories_to_exclude

        if amount_dec > 0:  # Income or positive transfer/payment
            income_by_category_dec[category] += amount_dec
            if not is_operational_exclusion:
                total_income_dec += amount_dec
            else:  # It's a positive payment/transfer (e.g., refund received, transfer in)
                total_payments_transfers_dec += amount_dec
        elif amount_dec < 0:  # Spending or negative transfer/payment
            # spending_by_category stores negative values, sum of absolute for display later
            spending_by_category_dec[category] += amount_dec
            if not is_operational_exclusion:
                total_spending_dec += amount_dec  # total_spending will be negative
            else:  # It's a negative payment/transfer (e.g., loan payment, transfer out)
                total_payments_transfers_dec += amount_dec

    summary["total_income"] = str(total_income_dec.quantize(Decimal("0.01")))
    summary["total_spending"] = str(total_spending_dec.quantize(Decimal("0.01")))  # Will be negative or zero
    summary["total_payments_transfers"] = str(total_payments_transfers_dec.quantize(Decimal("0.01")))
    summary["net_flow_operational"] = str(
        (total_income_dec + total_spending_dec).quantize(Decimal("0.01")))  # spending is negative
    summary["net_change_total"] = str(net_change_total_dec.quantize(Decimal("0.01")))

    summary["spending_by_category"] = {k: str(v.quantize(Decimal("0.01"))) for k, v in spending_by_category_dec.items()}
    summary["income_by_category"] = {k: str(v.quantize(Decimal("0.01"))) for k, v in income_by_category_dec.items()}

    if all_amounts_dec:
        summary["average_transaction_amount"] = str(
            (sum(all_amounts_dec) / len(all_amounts_dec)).quantize(Decimal("0.01")))
        sorted_amounts = sorted(all_amounts_dec)
        n = len(sorted_amounts)
        mid = n // 2
        if n % 2 == 1:
            summary["median_transaction_amount"] = str(sorted_amounts[mid].quantize(Decimal("0.01")))
        else:
            summary["median_transaction_amount"] = str(
                ((sorted_amounts[mid - 1] + sorted_amounts[mid]) / Decimal('2')).quantize(Decimal("0.01")))
    log.info("Summary insights calculation finished.")
    return summary


# --- Monthly Spending Trends ---
def calculate_monthly_spending_trends(transactions: List[Transaction]) -> Dict[str, Any]:
    log.info(f"Calculating monthly trends for {len(transactions)} transactions.")
    trends: Dict[str, Any] = {
        "start_date": None, "end_date": None,
        "monthly_spending": {}, "trend_comparison": None
    }
    if not transactions:
        log.warning("No transactions for trend calculation.")
        return trends

    # Determine overall start and end dates from the provided transactions
    valid_dates = sorted([tx.date for tx in transactions if tx.date is not None])
    if not valid_dates:
        log.warning("No valid dates in transactions for trend calculation.")
        return trends

    trends["start_date"] = valid_dates[0].isoformat()
    trends["end_date"] = valid_dates[-1].isoformat()

    monthly_data_dec = defaultdict(lambda: defaultdict(Decimal))
    # Define categories to exclude from "operational spending" in trends
    # These are typically transfers, payments between own accounts, or non-expense income.
    operational_spending_exclusions = ['Payments', 'Transfers', 'Ignore', 'Income', 'Internal Transfer',
                                       'Credit Card Payment']

    for tx in transactions:
        if tx.date is None or tx.amount is None or tx.amount >= 0:  # Only consider spending (negative amounts)
            continue
        if tx.category in operational_spending_exclusions:
            continue

        month_year_key = get_month_year_str(tx.date)
        if month_year_key is None: continue  # Should not happen if tx.date is not None

        category = tx.category if tx.category else 'Uncategorized'
        monthly_data_dec[month_year_key][category] += abs(tx.amount)  # Store as positive for spending
        monthly_data_dec[month_year_key]['__total__'] += abs(tx.amount)

    # Convert Decimals to strings for JSON output
    trends["monthly_spending"] = {
        month: {cat: str(val.quantize(Decimal("0.01"))) for cat, val in data.items()}
        for month, data in monthly_data_dec.items()
    }

    sorted_months = sorted(monthly_data_dec.keys())
    if len(sorted_months) >= 2:
        current_month_key = sorted_months[-1]
        previous_month_key = sorted_months[-2]
        current_data = monthly_data_dec[current_month_key]
        previous_data = monthly_data_dec[previous_month_key]
        comparison_details = {}
        all_categories_for_trend = set(current_data.keys()) | set(previous_data.keys())
        all_categories_for_trend.discard('__total__')

        for category in sorted(list(all_categories_for_trend)):
            current_amount = current_data.get(category, Decimal('0'))
            previous_amount = previous_data.get(category, Decimal('0'))
            change = current_amount - previous_amount
            percent_change = float((change / previous_amount) * 100) if previous_amount != 0 else None
            comparison_details[category] = {
                "current_amount": str(current_amount.quantize(Decimal("0.01"))),
                "previous_amount": str(previous_amount.quantize(Decimal("0.01"))),
                "change": str(change.quantize(Decimal("0.01"))),
                "percent_change": round(percent_change, 1) if percent_change is not None else None,
            }

        total_current = current_data.get('__total__', Decimal('0'))
        total_previous = previous_data.get('__total__', Decimal('0'))
        total_change = total_current - total_previous
        total_percent_change = float((total_change / total_previous) * 100) if total_previous != 0 else None

        trends["trend_comparison"] = {
            "current_month_str": current_month_key, "previous_month_str": previous_month_key,
            "total_current_spending": str(total_current.quantize(Decimal("0.01"))),
            "total_previous_spending": str(total_previous.quantize(Decimal("0.01"))),
            "total_change": str(total_change.quantize(Decimal("0.01"))),
            "total_percent_change": round(total_percent_change, 1) if total_percent_change is not None else None,
            "comparison": comparison_details
        }
    log.info("Monthly spending trend calculation finished.")
    return trends


# --- Recurring Transactions ---
def identify_recurring_transactions(transactions: List[Transaction],
                                    min_occurrences: int = 3,
                                    days_tolerance: int = 7,  # Increased tolerance for monthly
                                    amount_tolerance_percent: float = 15.0) -> Dict[str, List[Dict]]:
    log.info(
        f"Identifying recurring transactions (min_occ:{min_occurrences}, day_tol:{days_tolerance}, amt_tol%:{amount_tolerance_percent}).")
    if not transactions:
        return {"recurring_groups": []}

    # Group by cleaned description (lowercase, maybe remove some common prefixes/numbers later)
    grouped_by_desc: Dict[str, List[Transaction]] = defaultdict(list)
    for tx in transactions:
        if tx.description and tx.date and tx.amount is not None:
            # Basic cleaning: lowercase, strip. More advanced cleaning could be added.
            # Example: remove trailing numbers if they often change (e.g., "Netflix #123")
            clean_desc = tx.description.lower().strip()
            # clean_desc = re.sub(r'\s*\d+$', '', clean_desc) # Optional: remove trailing numbers
            # clean_desc = re.sub(r'#\w+', '', clean_desc) # Optional: remove hashtags or IDs
            grouped_by_desc[clean_desc].append(tx)

    potential_recurring_groups: List[Dict] = []

    for desc_key, group_txs in grouped_by_desc.items():
        if len(group_txs) < min_occurrences:
            continue
        group_txs.sort(key=lambda t: t.date)  # type: ignore

        # Sub-group by amount within tolerance
        # Key: representative amount (e.g., first transaction's amount in a cluster)
        # Value: list of transactions in that amount cluster
        amount_clusters: Dict[Decimal, List[Transaction]] = defaultdict(list)
        for tx in group_txs:
            matched_to_cluster = False
            for base_amount in list(amount_clusters.keys()):  # Iterate over copy of keys
                tolerance_value = abs(base_amount * (Decimal(str(amount_tolerance_percent)) / Decimal('100')))
                if abs(tx.amount - base_amount) <= tolerance_value:  # type: ignore
                    amount_clusters[base_amount].append(tx)
                    matched_to_cluster = True
                    break
            if not matched_to_cluster:
                amount_clusters[tx.amount].append(tx)  # type: ignore

        for base_amt, clustered_txs in amount_clusters.items():
            if len(clustered_txs) < min_occurrences:
                continue

            # Analyze intervals
            intervals_days: List[int] = []
            for i in range(len(clustered_txs) - 1):
                # clustered_txs is already sorted by date
                delta = clustered_txs[i + 1].date - clustered_txs[i].date  # type: ignore
                intervals_days.append(delta.days)

            if not intervals_days: continue  # Need at least two transactions to have an interval

            # Find the most common interval within tolerance
            # This is a simplification; more advanced methods exist (e.g., DBSCAN on intervals)
            interval_counts = Counter(intervals_days)
            most_common_raw_interval, _ = interval_counts.most_common(1)[0] if interval_counts else (None, 0)

            if most_common_raw_interval is None: continue

            # Group intervals that are close to the most_common_raw_interval
            consistent_intervals: List[int] = []
            for interval in intervals_days:
                if abs(interval - most_common_raw_interval) <= days_tolerance:
                    consistent_intervals.append(interval)

            # We need enough consistent intervals for min_occurrences
            # N occurrences means N-1 intervals.
            if len(consistent_intervals) >= min_occurrences - 1:
                avg_consistent_interval = round(sum(consistent_intervals) / len(
                    consistent_intervals)) if consistent_intervals else most_common_raw_interval

                # Calculate average amount for this specific recurring group
                avg_amount_for_group = sum(t.amount for t in clustered_txs) / len(clustered_txs)  # type: ignore

                potential_recurring_groups.append({
                    "description": desc_key,  # The original cleaned description key
                    "category": clustered_txs[0].category,  # Assume category is consistent for this group
                    "average_amount": str(avg_amount_for_group.quantize(Decimal("0.01"))),
                    "count": len(clustered_txs),
                    "interval_days": avg_consistent_interval,
                    "transactions": [t.to_dict() for t in clustered_txs]  # Convert Transaction objects to dicts
                })

    log.info(f"Identified {len(potential_recurring_groups)} potential recurring groups.")
    potential_recurring_groups.sort(key=lambda g: (g['count'], abs(Decimal(g['average_amount']))), reverse=True)
    return {"recurring_groups": potential_recurring_groups}


# --- Example Usage ---
if __name__ == "__main__":
    log.info("insights.py executed directly for testing.")

    # Dummy user_id for testing, as Transaction now requires it
    test_user_id_insights = "user_insights_tester_uuid"

    # Create some dummy transactions
    test_transactions = [
        Transaction(id=1, user_id=test_user_id_insights, date=dt.date(2025, 1, 15), description="NETFLIX",
                    amount=Decimal("-15.99"), category="Subscriptions"),
        Transaction(id=2, user_id=test_user_id_insights, date=dt.date(2025, 2, 14), description="NETFLIX",
                    amount=Decimal("-15.99"), category="Subscriptions"),
        Transaction(id=3, user_id=test_user_id_insights, date=dt.date(2025, 3, 15), description="NETFLIX",
                    amount=Decimal("-15.99"), category="Subscriptions"),
        Transaction(id=4, user_id=test_user_id_insights, date=dt.date(2025, 4, 15), description="NETFLIX",
                    amount=Decimal("-16.05"), category="Subscriptions"),
        Transaction(id=5, user_id=test_user_id_insights, date=dt.date(2025, 3, 1), description="Gym Membership",
                    amount=Decimal("-40.00"), category="Health"),
        Transaction(id=6, user_id=test_user_id_insights, date=dt.date(2025, 4, 1), description="Gym Membership",
                    amount=Decimal("-40.00"), category="Health"),
        Transaction(id=7, user_id=test_user_id_insights, date=dt.date(2025, 3, 7), description="Payroll",
                    amount=Decimal("2000.00"), category="Income"),
        Transaction(id=8, user_id=test_user_id_insights, date=dt.date(2025, 3, 21), description="Payroll",
                    amount=Decimal("2000.00"), category="Income"),
        Transaction(id=9, user_id=test_user_id_insights, date=dt.date(2025, 4, 7), description="Payroll",
                    amount=Decimal("2050.00"), category="Income"),
        Transaction(id=10, user_id=test_user_id_insights, date=dt.date(2025, 4, 10), description="Coffee Shop",
                    amount=Decimal("-5.00"), category="Food"),
        Transaction(id=11, user_id=test_user_id_insights, date=dt.date(2025, 4, 17), description="Coffee Shop",
                    amount=Decimal("-5.25"), category="Food"),
        Transaction(id=12, user_id=test_user_id_insights, date=dt.date(2025, 4, 24), description="Coffee Shop",
                    amount=Decimal("-4.90"), category="Food"),
        Transaction(id=13, user_id=test_user_id_insights, date=dt.date(2025, 4, 5), description="Payment Received",
                    amount=Decimal("500.00"), category="Payments"),
        Transaction(id=14, user_id=test_user_id_insights, date=dt.date(2025, 1, 5), description="Transfer to Savings",
                    amount=Decimal("-200.00"), category="Transfers"),
        Transaction(id=15, user_id=test_user_id_insights, date=dt.date(2025, 2, 5), description="Transfer to Savings",
                    amount=Decimal("-200.00"), category="Transfers"),
        Transaction(id=16, user_id=test_user_id_insights, date=dt.date(2025, 3, 5), description="Transfer to Savings",
                    amount=Decimal("-200.00"), category="Transfers"),
    ]

    print("\n--- Testing Summary Insights ---")
    summary = calculate_summary_insights(test_transactions)
    import json

    print(json.dumps(summary, indent=2))

    print("\n--- Testing Monthly Trends ---")
    trends = calculate_monthly_spending_trends(transactions=test_transactions)
    print(json.dumps(trends, indent=2))

    print("\n--- Testing Recurring Transactions ---")
    recurring = identify_recurring_transactions(test_transactions)
    print(json.dumps(recurring, indent=2))

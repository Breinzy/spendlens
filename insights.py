# insights.py

import logging
from collections import defaultdict, Counter
import datetime as dt
from dateutil.relativedelta import relativedelta
from decimal import Decimal, InvalidOperation
from typing import List, Dict, Any, Optional # Added Optional for type hints

# --- MOVED LOGGING CONFIGURATION UP ---
# Configure logging
log = logging.getLogger('insights') # Use specific logger name
log.setLevel(logging.INFO)
if not log.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)
# --- END OF MOVE ---

# --- Import Transaction Class Safely ---
# Attempt to import the real Transaction class from database or parser
# Define a placeholder if import fails, to prevent load-time errors
try:
    # Prioritize importing from database.py if it defines the class consistently
    from database import Transaction
    log.info("Successfully imported Transaction class from database module.") # Now log is defined
except ImportError:
    try:
        # Fallback to importing from parser.py
        from parser import Transaction
        log.info("Successfully imported Transaction class from parser module.") # Now log is defined
    except ImportError:
        log.warning("Could not import Transaction class from database or parser. Defining placeholder.") # Now log is defined
        # Define a placeholder class with expected attributes if import fails
        class Transaction:
            id: int = 0
            date: Optional[dt.date] = None
            description: Optional[str] = None
            amount: Optional[Decimal] = None
            category: Optional[str] = None
            transaction_type: Optional[str] = None
            # Add other attributes if your insights functions expect them

# --- Removed import of non-existent function ---
# from parser import _clean_description_for_rule # This function doesn't exist in parser.py


# --- Helper Function ---
def get_month_year_str(date_obj: dt.date) -> str:
    """Formats a date object into 'YYYY-MM' string."""
    return date_obj.strftime('%Y-%m')

# --- Summary Statistics ---
def calculate_summary_insights(transactions: List[Transaction]) -> Dict[str, Any]:
    """
    Calculates various summary statistics from a list of transactions.
    """
    log.info(f"Calculating summary insights for {len(transactions)} transactions.")
    summary = {
        "total_transactions": len(transactions),
        "period_start_date": None,
        "period_end_date": None,
        "total_income": Decimal('0'),
        "total_spending": Decimal('0'), # Operational spending (excludes Payments/Transfers)
        "total_payments_transfers": Decimal('0'), # Sum of Payments/Transfers
        "net_flow_operational": Decimal('0'), # Income - Operational Spending
        "net_change_total": Decimal('0'), # Sum of all amounts
        "spending_by_category": defaultdict(Decimal),
        "income_by_category": defaultdict(Decimal), # Track income sources if needed
        "average_transaction_amount": Decimal('0'),
        "median_transaction_amount": Decimal('0'),
    }

    if not transactions:
        log.warning("No transactions provided for summary calculation.")
        return summary # Return default summary if no transactions

    # Filter out transactions without a date before sorting
    valid_transactions = [tx for tx in transactions if tx.date is not None]
    if not valid_transactions:
        log.warning("No transactions with valid dates provided for summary calculation.")
        return summary

    # Sort transactions by date to find start/end
    valid_transactions.sort(key=lambda t: t.date) # type: ignore
    summary["period_start_date"] = valid_transactions[0].date.isoformat() if valid_transactions[0].date else None
    summary["period_end_date"] = valid_transactions[-1].date.isoformat() if valid_transactions[-1].date else None

    all_amounts = []
    operational_categories = ['Payments', 'Transfers', 'Ignore'] # Categories to exclude from operational spending/income

    for tx in valid_transactions: # Iterate over valid transactions
        if not hasattr(tx, 'amount') or tx.amount is None: continue # Skip transactions without amount attribute or None amount

        try:
            # Ensure amount is Decimal
            amount_dec = Decimal(tx.amount)
        except (InvalidOperation, TypeError):
            log.warning(f"Skipping transaction ID {getattr(tx, 'id', 'N/A')} due to invalid amount type: {tx.amount}")
            continue

        summary["net_change_total"] += amount_dec
        all_amounts.append(amount_dec)

        category = getattr(tx, 'category', 'Uncategorized') # Use getattr for safety

        # Accumulate totals based on category and amount sign
        if amount_dec > 0:
            summary["income_by_category"][category] += amount_dec
            if category not in operational_categories:
                 summary["total_income"] += amount_dec
            else:
                 summary["total_payments_transfers"] += amount_dec # Add positive payments/transfers here
        elif amount_dec < 0:
            summary["spending_by_category"][category] += amount_dec # Store spending as negative
            if category not in operational_categories:
                summary["total_spending"] += amount_dec # Add negative amount
            else:
                summary["total_payments_transfers"] += amount_dec # Add negative payments/transfers here


    # Calculate derived metrics
    summary["net_flow_operational"] = summary["total_income"] + summary["total_spending"] # spending is negative

    if all_amounts:
        try:
            summary["average_transaction_amount"] = sum(all_amounts) / len(all_amounts)
            # Calculate median
            sorted_amounts = sorted(all_amounts)
            n = len(sorted_amounts)
            mid = n // 2
            if n % 2 == 1:
                summary["median_transaction_amount"] = sorted_amounts[mid]
            else:
                # Ensure division by 2 results in Decimal
                summary["median_transaction_amount"] = (sorted_amounts[mid - 1] + sorted_amounts[mid]) / Decimal('2')
        except ZeroDivisionError:
             log.warning("Cannot calculate average transaction amount: list of amounts is empty.")
             summary["average_transaction_amount"] = Decimal('0')
             summary["median_transaction_amount"] = Decimal('0')


    # Convert defaultdicts to regular dicts and amounts to strings for JSON
    summary["spending_by_category"] = {k: str(v) for k, v in summary["spending_by_category"].items()}
    summary["income_by_category"] = {k: str(v) for k, v in summary["income_by_category"].items()}
    summary["total_income"] = str(summary["total_income"])
    summary["total_spending"] = str(summary["total_spending"])
    summary["total_payments_transfers"] = str(summary["total_payments_transfers"])
    summary["net_flow_operational"] = str(summary["net_flow_operational"])
    summary["net_change_total"] = str(summary["net_change_total"])
    summary["average_transaction_amount"] = str(summary["average_transaction_amount"])
    summary["median_transaction_amount"] = str(summary["median_transaction_amount"])


    log.info("Summary insights calculation finished.")
    return summary

# --- Monthly Spending Trends ---
def calculate_monthly_spending_trends(transactions: Optional[List[Transaction]] = None,
                                      start_date: Optional[dt.date] = None,
                                      end_date: Optional[dt.date] = None) -> Dict[str, Any]:
    """
    Calculates month-over-month spending trends by category.
    If transactions list is provided, uses it. Otherwise fetches from DB based on dates.
    """
    trends = {
        "start_date": None,
        "end_date": None,
        "monthly_spending": {}, # { 'YYYY-MM': {'category': Decimal(amount), ... , '__total__': Decimal(total)} }
        "trend_comparison": None # { 'category': {'current': Dec, 'previous': Dec, 'change': Dec, 'percent_change': float} }
    }
    using_fetched_transactions = False
    if transactions is None:
        using_fetched_transactions = True
        log.info("No transactions passed to trends calculation, fetching from DB.")
        # Fetch transactions if not provided, default to last 6 months if no dates
        today = dt.date.today()
        if end_date is None:
            end_date = today
        if start_date is None:
            start_date = end_date - relativedelta(months=6) + dt.timedelta(days=1) # Approx 6 months back

        trends["start_date"] = start_date.isoformat()
        trends["end_date"] = end_date.isoformat()
        # Import database locally to avoid potential circular dependency at module level
        try:
            import database as db
            transactions = db.get_all_transactions(start_date=start_date.isoformat(), end_date=end_date.isoformat())
        except ImportError:
            log.error("Failed to import database module within trends function.")
            return {"error": "Database module unavailable."}
        except Exception as e:
            log.error(f"Failed to fetch transactions for trends: {e}", exc_info=True)
            return {"error": "Failed to fetch transaction data."}

    # Ensure transactions is a list even if fetching failed or returned None
    if not isinstance(transactions, list):
        log.warning("Transaction data is not a list, cannot calculate trends.")
        transactions = []


    if not transactions:
        log.warning("No transactions available for trend calculation.")
        # If we fetched transactions and got none, update the trend dates
        if using_fetched_transactions:
             trends["start_date"] = start_date.isoformat() if start_date else None
             trends["end_date"] = end_date.isoformat() if end_date else None
        return trends

    log.info(f"Calculating monthly trends for {len(transactions)} transactions.")

    # Aggregate spending by month and category
    monthly_data = defaultdict(lambda: defaultdict(Decimal))
    operational_categories = ['Payments', 'Transfers', 'Ignore', 'Income'] # Exclude these from spending totals

    for tx in transactions:
        # Add checks for attributes existence
        if not hasattr(tx, 'date') or tx.date is None or \
           not hasattr(tx, 'amount') or tx.amount is None or \
           not hasattr(tx, 'category'):
            log.debug(f"Skipping trend calculation for transaction ID {getattr(tx, 'id', 'N/A')} due to missing attributes.")
            continue

        try:
            amount_dec = Decimal(tx.amount)
        except (InvalidOperation, TypeError):
            log.warning(f"Skipping trend calculation for transaction ID {getattr(tx, 'id', 'N/A')} due to invalid amount type: {tx.amount}")
            continue

        if amount_dec >= 0: # Only consider spending (negative amounts)
            continue
        if tx.category in operational_categories: # Exclude non-spending categories
             continue

        month_year = get_month_year_str(tx.date)
        category = tx.category if tx.category else 'Uncategorized'
        # Add the absolute spending amount
        monthly_data[month_year][category] += abs(amount_dec)
        monthly_data[month_year]['__total__'] += abs(amount_dec) # Track total spending per month

    # Sort months chronologically
    sorted_months = sorted(monthly_data.keys())
    trends["monthly_spending"] = {
        month: {cat: str(val) for cat, val in data.items()} # Convert Decimals to strings
        for month, data in monthly_data.items()
    }


    # Calculate comparison between the last two available months
    if len(sorted_months) >= 2:
        current_month = sorted_months[-1]
        previous_month = sorted_months[-2]
        log.info(f"Calculating trend comparison between {previous_month} and {current_month}.")

        current_data = monthly_data[current_month]
        previous_data = monthly_data[previous_month]
        comparison = {}
        all_categories = set(current_data.keys()) | set(previous_data.keys())
        all_categories.discard('__total__') # Don't compare the total key directly here

        for category in sorted(list(all_categories)): # Sort categories alphabetically
            current_amount = current_data.get(category, Decimal('0'))
            previous_amount = previous_data.get(category, Decimal('0'))
            change = current_amount - previous_amount
            percent_change = None
            if previous_amount != 0:
                try:
                    # Calculate percentage change, handle potential division by zero if previous is tiny
                    percent_change = float((change / previous_amount) * 100)
                except (InvalidOperation, OverflowError):
                     percent_change = None # Or set to infinity/large number if appropriate

            comparison[category] = {
                "current_amount": str(current_amount),
                "previous_amount": str(previous_amount),
                "change": str(change),
                "percent_change": percent_change # Keep as float/None
            }

        # Add overall total comparison
        total_current = current_data.get('__total__', Decimal('0'))
        total_previous = previous_data.get('__total__', Decimal('0'))
        total_change = total_current - total_previous
        total_percent_change = None
        if total_previous != 0:
             try:
                 total_percent_change = float((total_change / total_previous) * 100)
             except (InvalidOperation, OverflowError):
                  total_percent_change = None

        trends["trend_comparison"] = {
            "current_month_str": current_month,
            "previous_month_str": previous_month,
            "total_current_spending": str(total_current),
            "total_previous_spending": str(total_previous),
            "total_change": str(total_change),
            "total_percent_change": total_percent_change,
            "comparison": comparison
        }
    else:
        log.warning("Not enough monthly data (requires at least 2 months) to calculate trends.")


    log.info("Monthly spending trend calculation finished.")
    return trends


# --- Recurring Transactions ---
def identify_recurring_transactions(transactions: List[Transaction],
                                    min_occurrences: int = 3,
                                    days_tolerance: int = 5,
                                    amount_tolerance_percent: float = 10.0) -> Dict[str, List[Dict]]:
    """
    Identifies potential recurring transactions based on description similarity,
    amount proximity, and date intervals.
    """
    log.info(f"Identifying recurring transactions (min: {min_occurrences}, days tol: {days_tolerance}, amount tol: {amount_tolerance_percent}%).")
    if not transactions:
        return {"recurring_groups": []} # Return structure expected by app.py

    # Group transactions by a cleaned description key
    # Using a simple lowercase version for now, could be more sophisticated
    grouped_by_desc = defaultdict(list)
    for tx in transactions:
         # Ensure necessary attributes exist
        if hasattr(tx, 'description') and tx.description and \
           hasattr(tx, 'date') and tx.date and \
           hasattr(tx, 'amount') and tx.amount is not None:
            try:
                # Basic cleaning: lowercase, remove leading/trailing spaces
                clean_desc = tx.description.lower().strip()
                # Maybe remove common prefixes/suffixes like TST*, SQ*, etc.? Needs careful rules.
                grouped_by_desc[clean_desc].append(tx)
            except Exception as e:
                 log.warning(f"Skipping transaction ID {getattr(tx, 'id', 'N/A')} during grouping due to error: {e}")
                 continue

    potential_groups = []

    # Analyze groups with enough potential occurrences
    for desc, group_txs in grouped_by_desc.items():
        if len(group_txs) < min_occurrences:
            continue

        # Sort transactions within the group by date
        group_txs.sort(key=lambda t: t.date) # type: ignore

        # Check for recurring patterns within the group
        # This is a complex task. A simple approach: check intervals and amounts.
        # Iterate through transactions and try to form sequences
        # For simplicity, let's focus on amount similarity first
        amount_groups = defaultdict(list)
        for tx in group_txs:
             # Group by amount within tolerance
             matched_group = False
             try:
                 amount_dec = Decimal(tx.amount) # Ensure Decimal
                 for base_amount_str in list(amount_groups.keys()): # Iterate over copies of keys
                     base_amount = Decimal(base_amount_str) # Convert key back to Decimal
                     tolerance = abs(base_amount * (Decimal(amount_tolerance_percent) / 100))
                     if abs(amount_dec - base_amount) <= tolerance:
                         amount_groups[base_amount_str].append(tx) # Use string key
                         matched_group = True
                         break
                 if not matched_group:
                     amount_groups[str(amount_dec)].append(tx) # Start a new amount group using string key
             except (InvalidOperation, TypeError):
                  log.warning(f"Skipping transaction ID {getattr(tx, 'id', 'N/A')} in amount grouping due to invalid amount: {tx.amount}")
                  continue


        # Now analyze sequences within each amount group for consistent intervals
        for base_amount_str, amount_group_txs in amount_groups.items():
            if len(amount_group_txs) < min_occurrences:
                continue

            base_amount = Decimal(base_amount_str) # Convert key back for logging/output

            # Check date intervals (more complex logic needed here)
            # Example: Calculate days between consecutive transactions
            intervals = []
            if len(amount_group_txs) > 1:
                 for i in range(len(amount_group_txs) - 1):
                     # Ensure dates are valid before calculating delta
                     if amount_group_txs[i+1].date and amount_group_txs[i].date:
                         delta = amount_group_txs[i+1].date - amount_group_txs[i].date # type: ignore
                         intervals.append(delta.days)
                     else:
                          log.debug(f"Skipping interval calculation due to missing date in group: {desc}")


            # Look for a common interval (e.g., monthly ~30 days, bi-weekly ~14 days)
            # This requires more sophisticated analysis (e.g., clustering intervals)
            # Simplified check: If most intervals are within tolerance of a common value (e.g., 30 +/- days_tolerance)
            if not intervals: continue

            interval_counts = Counter(intervals)
            # Filter out potential outliers if needed
            # Find the most frequent interval within the tolerance range
            common_interval_found = None
            max_count = 0

            # Check common periods (weekly, bi-weekly, monthly, yearly)
            possible_periods = [7, 14, 15, 30, 31, 28, 29, 365, 366] # Approximate days
            best_fit_interval = None

            for period in possible_periods:
                current_count = 0
                intervals_in_period = []
                for interval, num in interval_counts.items():
                    if abs(interval - period) <= days_tolerance:
                        current_count += num
                        intervals_in_period.append(interval)
                if current_count >= min_occurrences - 1 and current_count > max_count: # Need N-1 intervals for N occurrences
                     max_count = current_count
                     # Calculate average of intervals close to the period
                     if intervals_in_period:
                          best_fit_interval = round(sum(intervals_in_period) / len(intervals_in_period))
                     else: # Should not happen if current_count > 0 but as fallback
                          best_fit_interval = period
                     common_interval_found = True


            if common_interval_found:
                potential_groups.append({
                    "description": desc,
                    "category": amount_group_txs[0].category, # Assume category is consistent
                    "average_amount": str(base_amount), # Use the base amount for the group
                    "count": len(amount_group_txs),
                    "interval_days": best_fit_interval, # Approximate interval
                    "transactions": [t.to_dict() for t in amount_group_txs] # Include tx details
                })

    log.info(f"Identified {len(potential_groups)} potential recurring groups.")
    # Sort groups perhaps by count or amount
    potential_groups.sort(key=lambda g: g['count'], reverse=True)
    return {"recurring_groups": potential_groups}


# --- Example Usage ---
if __name__ == "__main__":
    log.info("insights.py executed directly for testing.")

    # Create some dummy transactions
    # Use the Transaction class defined earlier in this file
    test_transactions = [
        Transaction(id=1, date=dt.date(2025, 1, 15), description="NETFLIX", amount=Decimal("-15.99"), category="Subscriptions"),
        Transaction(id=2, date=dt.date(2025, 2, 14), description="NETFLIX", amount=Decimal("-15.99"), category="Subscriptions"),
        Transaction(id=3, date=dt.date(2025, 3, 15), description="NETFLIX", amount=Decimal("-15.99"), category="Subscriptions"),
        Transaction(id=4, date=dt.date(2025, 4, 15), description="NETFLIX", amount=Decimal("-16.05"), category="Subscriptions"), # Slight amount change
        Transaction(id=5, date=dt.date(2025, 3, 1), description="Gym Membership", amount=Decimal("-40.00"), category="Health"),
        Transaction(id=6, date=dt.date(2025, 4, 1), description="Gym Membership", amount=Decimal("-40.00"), category="Health"),
        Transaction(id=7, date=dt.date(2025, 3, 7), description="Payroll", amount=Decimal("2000.00"), category="Income"),
        Transaction(id=8, date=dt.date(2025, 3, 21), description="Payroll", amount=Decimal("2000.00"), category="Income"),
        Transaction(id=9, date=dt.date(2025, 4, 7), description="Payroll", amount=Decimal("2050.00"), category="Income"), # Amount change
        Transaction(id=10, date=dt.date(2025, 4, 10), description="Coffee Shop", amount=Decimal("-5.00"), category="Food"),
        Transaction(id=11, date=dt.date(2025, 4, 17), description="Coffee Shop", amount=Decimal("-5.25"), category="Food"),
        Transaction(id=12, date=dt.date(2025, 4, 24), description="Coffee Shop", amount=Decimal("-4.90"), category="Food"),
        Transaction(id=13, date=dt.date(2025, 4, 5), description="Payment Received", amount=Decimal("500.00"), category="Payments"),
    ]

    print("\n--- Testing Summary Insights ---")
    summary = calculate_summary_insights(test_transactions)
    import json # Need json for printing dict nicely
    print(json.dumps(summary, indent=2))

    print("\n--- Testing Monthly Trends ---")
    trends = calculate_monthly_spending_trends(transactions=test_transactions)
    print(json.dumps(trends, indent=2))

    print("\n--- Testing Recurring Transactions ---")
    recurring = identify_recurring_transactions(test_transactions)
    print(json.dumps(recurring, indent=2))


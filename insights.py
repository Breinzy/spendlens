import logging
from collections import defaultdict, Counter
from decimal import Decimal, ROUND_HALF_UP
import datetime as dt
# Change: Import relativedelta if not already present
from dateutil.relativedelta import relativedelta
from typing import List, Dict, Tuple, Optional, Any

# Import the Transaction class definition from parser
try:
    from parser import Transaction, _clean_description_for_rule
except ImportError:
    logging.warning("Could not import Transaction or _clean_description_for_rule from parser. Assuming basic structure.")
    import re
    class Transaction: # Minimal definition
        def __init__(self, date, description, amount, category="Uncategorized", transaction_type=None, id=None, raw_description=None, **kwargs):
            self.id = id; self.date = date; self.description = description; self.raw_description = raw_description
            self.amount = Decimal(amount); self.category = category if category else "Uncategorized"; self.transaction_type = transaction_type
    def _clean_description_for_rule(description: str) -> str:
        if not description: return ""
        cleaned = re.sub(r'\s+\d{1,2}/\d{1,2}(?:/\d{2,4})?\s*$', '', description); cleaned = re.sub(r'\s{2,}', ' ', cleaned)
        return cleaned.strip()


# Define categories (lowercase)
TRANSFER_CATEGORIES = {"transfers", "payments"}
INCOME_CATEGORIES = {"income"}
# Change: Define categories likely to have recurring duplicates (e.g., subscriptions, maybe utilities)
DUPLICATE_CHECK_CATEGORIES = {"subscriptions", "utilities", "services", "fees & adjustments", "uncategorized"} # Add more as needed


def _validate_transactions(transactions: List[Transaction]) -> List[Transaction]:
    """Helper to ensure transactions have Decimal amounts."""
    # ... (validation logic remains the same) ...
    valid_transactions = []
    for tx in transactions:
        if not isinstance(tx.amount, Decimal):
            try: tx.amount = Decimal(tx.amount); valid_transactions.append(tx)
            except Exception as e: logging.warning(f"Skipping transaction during validation: {tx} | Error: {e}")
        else: valid_transactions.append(tx)
    return valid_transactions

def _is_operational_spending(tx: Transaction) -> bool:
    """Helper to determine if a transaction is operational spending."""
    category_lower = tx.category.lower() if isinstance(tx.category, str) else ""
    return tx.amount < 0 and category_lower not in TRANSFER_CATEGORIES

# (calculate_summary_insights function remains the same)
def calculate_summary_insights(transactions: List[Transaction]) -> Dict[str, any]:
    # ... (summary calculation logic remains the same) ...
    valid_transactions = _validate_transactions(transactions)
    operational_income = Decimal('0.00'); operational_spending = Decimal('0.00')
    transfers_in = Decimal('0.00'); transfers_out = Decimal('0.00')
    spending_by_category: Dict[str, Decimal] = defaultdict(Decimal)
    income_by_category: Dict[str, Decimal] = defaultdict(Decimal)
    refunds_by_category: Dict[str, Decimal] = defaultdict(Decimal)
    for tx in valid_transactions:
        category_lower = tx.category.lower() if isinstance(tx.category, str) else ""
        amount = tx.amount
        is_transfer_or_payment = category_lower in TRANSFER_CATEGORIES
        is_income_category = category_lower in INCOME_CATEGORIES
        is_likely_refund = amount > 0 and not is_income_category and not is_transfer_or_payment
        if amount > 0:
            income_by_category[tx.category] += amount
            if is_transfer_or_payment: transfers_in += amount
            elif is_income_category: operational_income += amount
            elif is_likely_refund: refunds_by_category[tx.category] += amount
            else: operational_income += amount
        elif _is_operational_spending(tx):
             operational_spending += abs(amount); spending_by_category[tx.category] += abs(amount)
        elif amount < 0: transfers_out += abs(amount)
    net_spending_by_category: Dict[str, Decimal] = defaultdict(Decimal)
    for category, spent in spending_by_category.items():
         if category.lower() not in TRANSFER_CATEGORIES:
            refunded = refunds_by_category.get(category, Decimal('0.00'))
            net_spending_by_category[category] = max(Decimal('0.00'), spent - refunded)
         else: net_spending_by_category[category] = spent
    net_operational_flow = operational_income - operational_spending
    net_transfer_flow = transfers_in - transfers_out
    def capitalize_dict_keys(d: Dict[str, Decimal]) -> Dict[str, Decimal]: return {k.title() if isinstance(k, str) else k: v for k, v in d.items()}
    summary = {
        "operational_income": operational_income, "operational_spending": operational_spending,
        "net_operational_flow": net_operational_flow, "transfers_in": transfers_in, "transfers_out": transfers_out,
        "net_transfer_flow": net_transfer_flow, "spending_by_category": capitalize_dict_keys(spending_by_category),
        "income_by_category": capitalize_dict_keys(income_by_category), "refunds_by_category": capitalize_dict_keys(refunds_by_category),
        "net_spending_by_category": capitalize_dict_keys(net_spending_by_category),
        "net_total_flow_all": net_operational_flow + net_transfer_flow, "transaction_count": len(valid_transactions) }
    return summary

# (calculate_monthly_trends function remains the same)
def calculate_monthly_trends(transactions: List[Transaction]) -> Dict[str, Any]:
    # ... (monthly trends calculation logic remains the same) ...
    valid_transactions = _validate_transactions(transactions)
    if not valid_transactions: return {"error": "No valid transactions provided."}
    transactions.sort(key=lambda tx: tx.date); latest_date = transactions[-1].date
    current_month_end = dt.date(latest_date.year, latest_date.month, 1) - dt.timedelta(days=1)
    current_month_start = dt.date(current_month_end.year, current_month_end.month, 1); current_month_str = current_month_start.strftime("%Y-%m")
    previous_month_end = current_month_start - dt.timedelta(days=1)
    previous_month_start = dt.date(previous_month_end.year, previous_month_end.month, 1); previous_month_str = previous_month_start.strftime("%Y-%m")
    logging.info(f"Calculating trends between {previous_month_str} and {current_month_str}")
    spending_current: Dict[str, Decimal] = defaultdict(Decimal); spending_previous: Dict[str, Decimal] = defaultdict(Decimal)
    all_categories_in_period = set()
    for tx in valid_transactions:
        if not isinstance(tx.date, dt.date): continue
        net_op_spending_impact = Decimal('0.00')
        category_lower = tx.category.lower() if isinstance(tx.category, str) else ""
        amount = tx.amount; is_transfer_or_payment = category_lower in TRANSFER_CATEGORIES; is_income_category = category_lower in INCOME_CATEGORIES
        is_likely_refund = amount > 0 and not is_income_category and not is_transfer_or_payment
        if amount < 0 and not is_transfer_or_payment: net_op_spending_impact = abs(amount)
        elif is_likely_refund: net_op_spending_impact = -amount
        if net_op_spending_impact != Decimal('0.00'):
            category_key = tx.category.title() if tx.category else "Uncategorized"
            if previous_month_start <= tx.date <= previous_month_end: spending_previous[category_key] += net_op_spending_impact; all_categories_in_period.add(category_key)
            elif current_month_start <= tx.date <= current_month_end: spending_current[category_key] += net_op_spending_impact; all_categories_in_period.add(category_key)
    if not any(previous_month_start <= tx.date <= previous_month_end for tx in valid_transactions) or \
       not any(current_month_start <= tx.date <= current_month_end for tx in valid_transactions):
        logging.warning("Insufficient data spanning the required two full months."); return {"error": "Insufficient data: Less than two full months of spending data available."}
    trends_list = []; quantize_decimal = Decimal("0.01")
    for category in sorted(list(all_categories_in_period)):
        prev_spend = max(Decimal('0.00'), spending_previous.get(category, Decimal('0.00'))).quantize(quantize_decimal, rounding=ROUND_HALF_UP)
        curr_spend = max(Decimal('0.00'), spending_current.get(category, Decimal('0.00'))).quantize(quantize_decimal, rounding=ROUND_HALF_UP)
        change_amount = curr_spend - prev_spend; change_percent = None
        if prev_spend > 0: change_percent = float(round((change_amount / prev_spend) * 100, 1))
        elif curr_spend > 0: change_percent = float('inf')
        if prev_spend > 0 or curr_spend > 0: trends_list.append({"category": category, "current_month_spending": curr_spend, "previous_month_spending": prev_spend, "change_amount": change_amount, "change_percent": change_percent})
    trends_list.sort(key=lambda x: x['category'])
    logging.info(f"Calculated trends for {len(trends_list)} categories.")
    return {"current_month": current_month_str, "previous_month": previous_month_str, "trends": trends_list}

# (identify_recurring_transactions function remains the same)
def identify_recurring_transactions(transactions: List[Transaction], min_occurrences: int = 3, days_tolerance: int = 3, amount_tolerance_percent: float = 5.0) -> List[Dict[str, Any]]:
    # ... (recurring identification logic remains the same) ...
    valid_transactions = _validate_transactions(transactions)
    if not valid_transactions: return []
    grouped: Dict[Tuple[str, bool], List[Tuple[dt.date, Decimal, str]]] = defaultdict(list)
    for tx in valid_transactions:
        if tx.category.lower() in TRANSFER_CATEGORIES: continue
        cleaned_desc = _clean_description_for_rule(tx.description);
        if not cleaned_desc: continue
        is_income = tx.amount > 0; group_key = (cleaned_desc.lower(), is_income)
        grouped[group_key].append((tx.date, tx.amount, tx.category))
    recurring = []; quantize_decimal = Decimal("0.01")
    for (desc_lower, is_income_group), tx_list in grouped.items():
        if len(tx_list) < min_occurrences: continue
        tx_list.sort(key=lambda x: x[0])
        amounts = [item[1] for item in tx_list]; avg_amount = sum(amounts) / len(amounts)
        if avg_amount == Decimal('0'): continue
        amount_tolerance_value = abs(avg_amount * (Decimal(amount_tolerance_percent) / Decimal(100)))
        if not all(abs(amount - avg_amount) <= amount_tolerance_value for amount in amounts): continue
        dates = [item[0] for item in tx_list]; intervals = [(dates[i+1] - dates[i]).days for i in range(len(dates) - 1)]
        if not intervals: continue
        avg_interval = sum(intervals) / len(intervals); consistent_interval = True; monthly_avg = 30.437
        if abs(avg_interval - monthly_avg) > days_tolerance * 2: consistent_interval = False
        if consistent_interval:
            if not all(abs(interval - avg_interval) <= days_tolerance for interval in intervals): consistent_interval = False
        if consistent_interval:
            categories = [item[2] for item in tx_list]; most_common_category = Counter(categories).most_common(1)[0][0]
            display_description = desc_lower.title()
            for tx in valid_transactions:
                 if _clean_description_for_rule(tx.description).lower() == desc_lower: display_description = tx.description; break
            recurring.append({"description": display_description, "category": most_common_category.title(), "average_amount": avg_amount.quantize(quantize_decimal, rounding=ROUND_HALF_UP), "count": len(tx_list), "dates": [d.isoformat() for d in dates], "estimated_interval_days": round(avg_interval, 1), "is_income": is_income_group})
    recurring.sort(key=lambda x: (-x['count'], x['description']))
    return recurring

# (analyze_frequent_spending function remains the same)
def analyze_frequent_spending(transactions: List[Transaction], start_date: Optional[dt.date] = None, end_date: Optional[dt.date] = None, min_frequency: int = 2) -> List[Dict[str, Any]]:
    # ... (frequent spending analysis logic remains the same) ...
    valid_transactions = _validate_transactions(transactions);
    if not valid_transactions: return []
    filtered_txs = []
    if start_date or end_date:
        for tx in valid_transactions:
            if not isinstance(tx.date, dt.date): continue
            if start_date and tx.date < start_date: continue
            if end_date and tx.date > end_date: continue
            filtered_txs.append(tx)
        logging.info(f"Filtered down to {len(filtered_txs)} transactions for frequent spending analysis.")
    else: filtered_txs = valid_transactions; logging.info(f"Analyzing {len(filtered_txs)} transactions for frequent spending.")
    spending_groups: Dict[str, List[Tuple[Decimal, str, Optional[int]]]] = defaultdict(list)
    for tx in filtered_txs:
        if _is_operational_spending(tx):
            group_key = tx.description.title() if isinstance(tx.description, str) else "Unknown Description"
            category_val = tx.category if isinstance(tx.category, str) else "Uncategorized"
            spending_groups[group_key].append((tx.amount, category_val, tx.id))
    frequent_spending = []; quantize_decimal = Decimal("0.01")
    for description, group_txs in spending_groups.items():
        frequency = len(group_txs)
        if frequency >= min_frequency:
            total = sum(abs(item[0]) for item in group_txs); average = total / frequency
            categories = [item[1] for item in group_txs]; valid_categories = [c for c in categories if c]
            most_common_category = Counter(valid_categories).most_common(1)[0][0] if valid_categories else "Uncategorized"
            transaction_ids = [item[2] for item in group_txs if item[2] is not None]
            frequent_spending.append({"cleaned_description": description, "frequency": frequency, "total_spending": total.quantize(quantize_decimal, rounding=ROUND_HALF_UP), "average_spending": average.quantize(quantize_decimal, rounding=ROUND_HALF_UP), "most_common_category": most_common_category.title(), "transaction_ids": transaction_ids})
    frequent_spending.sort(key=lambda x: (x['frequency'], x['total_spending']), reverse=True)
    logging.info(f"Identified {len(frequent_spending)} frequent spending patterns (min_freq={min_frequency}).")
    return frequent_spending


# --- Change: Add Duplicate Recurring Detection ---
def find_potential_duplicate_recurring(
    recurring_transactions: List[Dict[str, Any]],
    amount_similarity_percent: float = 10.0, # How close amounts need to be (%)
    max_days_apart_in_month: int = 7 # Max days between potential duplicates within the same month
) -> List[Dict[str, Any]]:
    """
    Analyzes a list of identified recurring transactions to find potential duplicates.

    Args:
        recurring_transactions: The output list from identify_recurring_transactions.
        amount_similarity_percent: Maximum percentage difference allowed between amounts.
        max_days_apart_in_month: Maximum number of days allowed between two occurrences
                                 within the same calendar month to be flagged as potential duplicates.

    Returns:
        A list of dictionaries, each representing a group of potential duplicates:
        [
            {
                "category": str,
                "potential_duplicates": [
                    # List of the original recurring transaction dicts that are potential duplicates
                    { recurring_transaction_dict_1 },
                    { recurring_transaction_dict_2 },
                    ...
                ],
                "reason": "Multiple recurring items found in the same category with similar amounts."
            }, ...
        ]
    """
    potential_duplicates = []
    # Group recurring items by category (lowercase for comparison)
    grouped_by_category: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for item in recurring_transactions:
        # Only check categories prone to duplicates and non-income items
        category_lower = item['category'].lower()
        if category_lower in DUPLICATE_CHECK_CATEGORIES and not item['is_income']:
            grouped_by_category[category_lower].append(item)

    # Analyze categories with multiple recurring items
    for category_lower, items in grouped_by_category.items():
        if len(items) > 1:
            # Check for amount similarity between pairs within the category
            checked_pairs = set() # Avoid checking pairs twice (a,b) and (b,a)
            possible_group = [] # Store items that might belong to a duplicate group

            for i in range(len(items)):
                for j in range(i + 1, len(items)):
                    item1 = items[i]
                    item2 = items[j]
                    pair_key = tuple(sorted((i, j))) # Unique key for the pair
                    if pair_key in checked_pairs: continue
                    checked_pairs.add(pair_key)

                    # Check amount similarity
                    avg1 = item1['average_amount']
                    avg2 = item2['average_amount']
                    # Avoid division by zero if an amount is zero
                    if avg1 == 0 or avg2 == 0: continue

                    amount_diff_percent = abs(avg1 - avg2) / max(abs(avg1), abs(avg2)) * 100
                    if amount_diff_percent <= amount_similarity_percent:
                        # Amounts are similar, check if dates overlap suspiciously
                        # A simple check: do any dates occur within the same month and close together?
                        dates1 = [dt.date.fromisoformat(d) for d in item1['dates']]
                        dates2 = [dt.date.fromisoformat(d) for d in item2['dates']]
                        found_suspicious_overlap = False
                        for d1 in dates1:
                            for d2 in dates2:
                                if d1.year == d2.year and d1.month == d2.month:
                                    if abs((d1 - d2).days) <= max_days_apart_in_month:
                                        found_suspicious_overlap = True
                                        break
                            if found_suspicious_overlap: break

                        if found_suspicious_overlap:
                             # Add both items to the potential group if not already added
                             if item1 not in possible_group: possible_group.append(item1)
                             if item2 not in possible_group: possible_group.append(item2)
                             logging.info(f"Potential duplicate found in category '{item1['category']}': '{item1['description']}' and '{item2['description']}' (Similar amount & close dates)")


            # If we found potential duplicates in this category group
            if possible_group:
                 potential_duplicates.append({
                     "category": possible_group[0]['category'], # Use category from first item
                     "potential_duplicates": possible_group,
                     "reason": f"Found {len(possible_group)} recurring items in the '{possible_group[0]['category']}' category with similar average amounts and occurrences within {max_days_apart_in_month} days in the same month."
                 })

    logging.info(f"Identified {len(potential_duplicates)} groups of potential duplicate recurring transactions.")
    return potential_duplicates


# (Testing block remains the same, add test for duplicates)
if __name__ == '__main__':
    # ... (previous dummy data and tests) ...
    import datetime as dt
    from decimal import Decimal
    import json

    if 'Transaction' not in globals():
        class Transaction:
            def __init__(self, date, description, amount, category="Uncategorized", transaction_type=None, id=None, raw_description=None, **kwargs):
                self.id=id; self.date=date; self.description=description; self.raw_description=raw_description
                self.amount=Decimal(amount); self.category=category if category else "Uncategorized"; self.transaction_type=transaction_type

    # Dummy data specifically for duplicate testing
    duplicate_test_data = [
        # Spotify - Should be identified as recurring
        Transaction(id=801, date=dt.date(2024, 1, 19), description="Spotify USA", amount=Decimal("-10.99"), category="Subscriptions"),
        Transaction(id=802, date=dt.date(2024, 2, 19), description="Spotify USA", amount=Decimal("-10.99"), category="Subscriptions"),
        Transaction(id=803, date=dt.date(2024, 3, 19), description="Spotify USA", amount=Decimal("-10.99"), category="Subscriptions"),
        Transaction(id=804, date=dt.date(2024, 4, 19), description="Spotify USA", amount=Decimal("-10.99"), category="Subscriptions"),

        # Duplicate Spotify? (Slightly different name, similar amount, close date in April)
        Transaction(id=901, date=dt.date(2024, 1, 21), description="SPOTIFYAB", amount=Decimal("-10.71"), category="Subscriptions"),
        Transaction(id=902, date=dt.date(2024, 2, 21), description="SPOTIFYAB", amount=Decimal("-10.71"), category="Subscriptions"),
        Transaction(id=903, date=dt.date(2024, 3, 21), description="SPOTIFYAB", amount=Decimal("-10.71"), category="Subscriptions"),
        Transaction(id=904, date=dt.date(2024, 4, 21), description="SPOTIFYAB", amount=Decimal("-10.71"), category="Subscriptions"), # Close to 804

        # Another Subscription - different amount/timing
        Transaction(id=1001, date=dt.date(2024, 1, 1), description="Cloud Storage", amount=Decimal("-5.00"), category="Subscriptions"),
        Transaction(id=1002, date=dt.date(2024, 2, 1), description="Cloud Storage", amount=Decimal("-5.00"), category="Subscriptions"),
        Transaction(id=1003, date=dt.date(2024, 3, 1), description="Cloud Storage", amount=Decimal("-5.00"), category="Subscriptions"),
        Transaction(id=1004, date=dt.date(2024, 4, 1), description="Cloud Storage", amount=Decimal("-5.00"), category="Subscriptions"),

        # Utility Bill - Recurring but not a duplicate candidate usually
        Transaction(id=1101, date=dt.date(2024, 1, 5), description="Electric Bill", amount=Decimal("-90.00"), category="Utilities"),
        Transaction(id=1102, date=dt.date(2024, 2, 5), description="Electric Bill", amount=Decimal("-95.00"), category="Utilities"),
        Transaction(id=1103, date=dt.date(2024, 3, 5), description="Electric Bill", amount=Decimal("-88.00"), category="Utilities"),
        Transaction(id=1104, date=dt.date(2024, 4, 5), description="Electric Bill", amount=Decimal("-92.00"), category="Utilities"),
    ]

    print("\n--- Identifying Recurring Transactions for Duplicate Check ---")
    recurring_items = identify_recurring_transactions(duplicate_test_data)
    print(f"Found {len(recurring_items)} recurring items:")
    print(json.dumps(recurring_items, indent=2, default=str))


    print("\n--- Finding Potential Duplicate Recurring Transactions ---")
    duplicates = find_potential_duplicate_recurring(recurring_items)
    print(f"Found {len(duplicates)} groups of potential duplicates:")
    print(json.dumps(duplicates, indent=2, default=str))


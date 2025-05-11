# insights.py
import logging
from collections import defaultdict, Counter
import datetime as dt
from dateutil.relativedelta import relativedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import List, Dict, Any, Optional, TypedDict  # Added TypedDict

# Project specific imports (ensure database_supabase is accessible)
try:
    import database_supabase as db_supabase
except ImportError:
    log = logging.getLogger('insights')
    log.critical("Failed to import database_supabase. Monthly revenue trend will not work.")


    # Define a fallback or raise an error if db_supabase is critical for all functions
    class db_supabase:  # type: ignore
        @staticmethod
        def get_revenue_for_past_n_months(user_id: str, num_months: int, data_context: Optional[str] = 'business') -> \
        Dict[str, Decimal]:
            return {}

        @staticmethod
        def get_revenue_current_month_to_date(user_id: str, data_context: Optional[str] = 'business') -> Decimal:
            return Decimal('0')

# Configure logging
log = logging.getLogger('insights')
log.setLevel(logging.INFO)  # Or settings.LOG_LEVEL if you have it
if not log.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s:%(funcName)s] - %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)

# --- Transaction Class Definition ---
# This should be consistent with parser.py and database_supabase.py
# If imported from parser, ensure parser.Transaction is complete.
# For robustness, especially if insights.py might be run independently or tested,
# a complete definition here (matching parser.py) is good.

try:
    from parser import Transaction as ParserTransaction

    # Check if ParserTransaction has all necessary fields, otherwise use the local one
    if not all(hasattr(ParserTransaction(user_id="test"), attr) for attr in
               ['rate', 'quantity', 'invoice_status', 'date_paid']):
        log.warning("parser.Transaction might be missing fields. Using local Transaction definition in insights.py.")
        raise ImportError("Using local Transaction due to potentially incomplete parser.Transaction")
    Transaction = ParserTransaction  # Use the one from parser if complete
    log.info("Successfully imported and using Transaction class from parser module for insights.")
except ImportError:
    log.warning(
        "Could not import Transaction class from parser.py or it was incomplete. Defining a local basic Transaction class for insights module.")


    class Transaction:
        def __init__(self, id: Optional[int], user_id: str, date: Optional[dt.date],
                     description: Optional[str], amount: Optional[Decimal], category: Optional[str],
                     client_name: Optional[str] = None,
                     # --- Ensure all relevant fields are here ---
                     rate: Optional[Decimal] = None,
                     quantity: Optional[Decimal] = None,
                     invoice_id: Optional[str] = None,
                     invoice_status: Optional[str] = None,
                     date_paid: Optional[dt.date] = None,
                     project_id: Optional[str] = None,
                     transaction_origin: Optional[str] = None,
                     raw_description: Optional[str] = None,
                     # Add any other fields used by insights functions
                     transaction_type: Optional[str] = None
                     ):
            self.id = id
            self.user_id = user_id
            self.date = date
            self.description = description
            self.amount = amount
            self.category = category
            self.client_name = client_name
            self.rate = rate
            self.quantity = quantity
            self.invoice_id = invoice_id
            self.invoice_status = invoice_status
            self.date_paid = date_paid
            self.project_id = project_id
            self.transaction_origin = transaction_origin
            self.raw_description = raw_description if raw_description else description
            self.transaction_type = transaction_type

        def to_dict(self) -> Dict[str, Any]:
            # Simplified to_dict for this local class if needed for debugging
            return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}


# --- TypedDict for Monthly Revenue Data Item (matches frontend interface) ---
class MonthlyRevenueDataItem(TypedDict):
    month: str  # Format "YYYY-MM" or "Current"
    revenue: float  # Store as float for JSON compatibility, or keep Decimal and convert at API layer
    isCurrent: Optional[bool]


# --- NEW FUNCTION: Calculate Monthly Revenue Trend ---
def calculate_monthly_revenue_trend(user_id: str, num_past_months: int, data_context: Optional[str] = 'business') -> \
List[MonthlyRevenueDataItem]:
    """
    Calculates revenue for the past N months and the current month-to-date.
    """
    log.info(
        f"User {user_id}: Calculating monthly revenue trend for past {num_past_months} months and current MTD. Context: {data_context}")

    trend_data: List[MonthlyRevenueDataItem] = []

    # Get revenue for past N full months
    past_revenues_decimal = db_supabase.get_revenue_for_past_n_months(user_id, num_past_months, data_context)

    # Sort by month (YYYY-MM string sort works correctly here)
    # and convert to list of MonthlyRevenueDataItem
    for month_str, revenue_decimal in sorted(past_revenues_decimal.items()):
        trend_data.append({
            "month": month_str,
            "revenue": float(revenue_decimal.quantize(Decimal("0.01"))),  # Convert Decimal to float for JSON
            "isCurrent": False
        })

    # Get current month-to-date revenue
    current_mtd_revenue_decimal = db_supabase.get_revenue_current_month_to_date(user_id, data_context)
    trend_data.append({
        "month": "Current",  # Special label for the current month
        "revenue": float(current_mtd_revenue_decimal.quantize(Decimal("0.01"))),
        "isCurrent": True
    })

    log.debug(f"User {user_id}: Generated monthly revenue trend data: {trend_data}")
    return trend_data


# --- Helper Function (get_month_year_str - as before) ---
def get_month_year_str(date_obj: Optional[dt.date]) -> Optional[str]:
    if date_obj is None: return None
    return date_obj.strftime('%Y-%m')


# --- Core Metrics Calculation (_calculate_core_financial_metrics - as before) ---
def _calculate_core_financial_metrics(transactions: List[Transaction]) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {
        "total_income": Decimal('0'),
        "total_spending": Decimal('0'),
        "net_flow_operational": Decimal('0'),
        "spending_by_category": defaultdict(Decimal),
        "income_by_category": defaultdict(Decimal),
    }
    if not transactions:
        metrics["spending_by_category"] = dict(metrics["spending_by_category"])
        metrics["income_by_category"] = dict(metrics["income_by_category"])
        return metrics

    operational_categories_to_exclude = ['Payments', 'Transfers', 'Ignore', 'Internal Transfer']

    for tx in transactions:
        if tx.amount is None: continue
        # Ensure tx.amount is Decimal
        amount_dec = tx.amount if isinstance(tx.amount, Decimal) else Decimal(str(tx.amount))
        category = tx.category if tx.category else 'Uncategorized'
        is_operational_exclusion = category in operational_categories_to_exclude

        if amount_dec > 0:
            metrics["income_by_category"][category] += amount_dec
            if not is_operational_exclusion:
                metrics["total_income"] += amount_dec
        elif amount_dec < 0:
            metrics["spending_by_category"][category] += amount_dec  # Spending is negative
            if not is_operational_exclusion:
                metrics["total_spending"] += amount_dec  # total_spending accumulates negative values

    metrics["net_flow_operational"] = metrics["total_income"] + metrics["total_spending"]  # total_spending is negative
    metrics["spending_by_category"] = dict(metrics["spending_by_category"])
    metrics["income_by_category"] = dict(metrics["income_by_category"])
    return metrics


# --- Revenue by Client (calculate_revenue_by_client - as before) ---
def calculate_revenue_by_client(transactions: List[Transaction]) -> Dict[str, Decimal]:
    revenue_by_client_dec = defaultdict(Decimal)
    if not transactions: return {}
    for tx in transactions:
        if tx.amount is not None and tx.amount > 0 and tx.client_name:
            client = tx.client_name.strip() if tx.client_name else "Unknown Client"
            revenue_by_client_dec[client] += tx.amount
    log.debug(f"Calculated revenue for {len(revenue_by_client_dec)} clients.")
    return dict(revenue_by_client_dec)


# --- Revenue by Service/Item (calculate_revenue_by_service - as before) ---
def calculate_revenue_by_service(transactions: List[Transaction]) -> Dict[str, Decimal]:
    revenue_by_service_dec = defaultdict(Decimal)
    if not transactions: return {}
    for tx in transactions:
        if tx.amount is not None and tx.amount > 0 and tx.description:
            service_item = tx.description.strip()
            revenue_by_service_dec[service_item] += tx.amount
    log.debug(f"Calculated revenue for {len(revenue_by_service_dec)} services/items.")
    return dict(revenue_by_service_dec)


# --- Revenue by Project (calculate_revenue_by_project - as before) ---
def calculate_revenue_by_project(transactions: List[Transaction]) -> Dict[str, Decimal]:
    revenue_by_project_dec = defaultdict(Decimal)
    if not transactions: return {}
    for tx in transactions:
        if tx.amount is not None and tx.amount > 0 and tx.project_id:
            project = tx.project_id.strip() if tx.project_id else "Unspecified Project"
            revenue_by_project_dec[project] += tx.amount
    log.debug(f"Calculated revenue for {len(revenue_by_project_dec)} projects.")
    return dict(revenue_by_project_dec)


# --- Client Rate Analysis (calculate_client_rate_insights - as before) ---
# Ensure this function correctly handles tx.rate and tx.quantity which should now be present
def calculate_client_rate_insights(transactions: List[Transaction]) -> Dict[str, Any]:
    client_rates_data: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"rates": [], "total_weighted_rate": Decimal(0), "total_quantity_for_avg": Decimal(0)})
    if not transactions: return {"rates_by_client": {}, "best_average_rate_client": None}

    for tx in transactions:
        # CRITICAL: Check if tx object actually has 'rate' and 'quantity' attributes
        # This depends on the Transaction class instance being passed in.
        # The local Transaction class has them, but if parser.Transaction is used, it must also.
        tx_rate = getattr(tx, 'rate', None)
        tx_quantity = getattr(tx, 'quantity', None)

        if tx.client_name and tx_rate is not None and tx_rate > 0:
            client = tx.client_name.strip()
            client_rates_data[client]["rates"].append(tx_rate)
            quantity_for_weight = tx_quantity if tx_quantity is not None and tx_quantity > 0 else Decimal(1)
            client_rates_data[client]["total_weighted_rate"] += tx_rate * quantity_for_weight
            client_rates_data[client]["total_quantity_for_avg"] += quantity_for_weight

    processed_client_rates: Dict[str, Dict[str, str]] = {}
    best_avg_rate = Decimal("-1")
    best_avg_rate_client_name: Optional[str] = None
    for client, data in client_rates_data.items():
        if data["rates"]:
            avg_rate = (data["total_weighted_rate"] / data["total_quantity_for_avg"]) if data[
                                                                                             "total_quantity_for_avg"] > 0 else (
                        sum(data["rates"]) / len(data["rates"]))
            max_rate = max(data["rates"])
            min_rate = min(data["rates"])
            processed_client_rates[client] = {
                "average_rate": str(avg_rate.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                "max_rate": str(max_rate.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                "min_rate": str(min_rate.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                "num_transactions_with_rate": str(len(data["rates"]))
            }
            if avg_rate > best_avg_rate:
                best_avg_rate = avg_rate
                best_avg_rate_client_name = client

    best_client_details = None
    if best_avg_rate_client_name and best_avg_rate_client_name in processed_client_rates:
        best_client_details = {"name": best_avg_rate_client_name,
                               "average_rate": processed_client_rates[best_avg_rate_client_name]["average_rate"]}

    log.debug(f"Calculated rate insights for {len(processed_client_rates)} clients.")
    return {"rates_by_client": processed_client_rates, "best_average_rate_client": best_client_details}


# --- Payment Status Summary (calculate_payment_status_summary - as before) ---
# Ensure this function correctly handles tx.invoice_status and tx.date_paid
def calculate_payment_status_summary(transactions: List[Transaction], today_date: Optional[dt.date] = None) -> Dict[
    str, Any]:
    if today_date is None: today_date = dt.date.today()
    invoice_data: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"total_amount": Decimal(0), "status": None, "date_issued": None, "date_paid": None})
    for tx in transactions:
        # CRITICAL: Check for invoice_id, invoice_status, date_paid
        tx_invoice_id = getattr(tx, 'invoice_id', None)
        tx_invoice_status = getattr(tx, 'invoice_status', None)
        tx_date_paid = getattr(tx, 'date_paid', None)

        if tx_invoice_id and tx.amount is not None:
            inv_id = tx_invoice_id
            invoice_data[inv_id]["total_amount"] += tx.amount  # Assuming amount is relevant to invoice total
            if invoice_data[inv_id]["status"] is None:  # Only set status/dates once per invoice
                invoice_data[inv_id]["status"] = tx_invoice_status.lower() if tx_invoice_status else "unknown"
                invoice_data[inv_id]["date_issued"] = tx.date  # Assuming tx.date is the invoice issue date
                invoice_data[inv_id]["date_paid"] = tx_date_paid

    status_summary: Dict[str, Decimal] = defaultdict(Decimal)
    total_outstanding = Decimal(0)
    total_overdue = Decimal(0)
    payment_terms_days = 30

    for inv_id, data in invoice_data.items():
        status = data["status"]
        amount = data["total_amount"]  # This might be line item amount, not total invoice amount if tx are line items
        date_issued = data["date_issued"]

        status_summary[status] += amount

        if status in ["sent", "viewed", "partial"] and not data["date_paid"]:  # Outstanding
            total_outstanding += amount
            if date_issued and (today_date - date_issued).days > payment_terms_days:
                total_overdue += amount
        elif status == "overdue":  # Explicitly overdue
            total_outstanding += amount
            total_overdue += amount

    log.debug(f"Calculated payment status summary for {len(invoice_data)} unique invoices.")
    return {
        "by_status": {k: str(v.quantize(Decimal("0.01"))) for k, v in status_summary.items()},
        "total_outstanding": str(total_outstanding.quantize(Decimal("0.01"))),
        "total_overdue": str(total_overdue.quantize(Decimal("0.01")))
    }


# --- Main Summary Function (calculate_summary_insights - as before) ---
# This function should now correctly receive Transaction objects with all fields
def calculate_summary_insights(
        current_period_transactions: List[Transaction],
        previous_period_transactions: Optional[List[Transaction]] = None,
        current_period_label: str = "Current Period",
        previous_period_label: str = "Previous Period"
) -> Dict[str, Any]:
    log.info(f"Calculating summary insights for current period ({len(current_period_transactions)} transactions).")
    if previous_period_transactions:
        log.info(f"Also calculating for previous period ({len(previous_period_transactions)} transactions).")

    # Initialize summary structure
    summary: Dict[str, Any] = {
        "total_transactions": 0, "period_start_date": None, "period_end_date": None,
        "total_income": "0.00", "total_spending": "0.00",  # total_spending will be negative or zero
        "net_flow_operational": "0.00",
        "spending_by_category": {}, "income_by_category": {},
        "revenue_by_client": {}, "revenue_by_service": {}, "revenue_by_project": {},
        "client_rate_analysis": {}, "payment_status_summary": {},
        "average_transaction_amount": "0.00", "median_transaction_amount": "0.00",
        "executive_summary": {}, "previous_period_comparison": None
    }

    if not current_period_transactions:
        log.warning("No transactions provided for current period summary calculation.")
        return summary

    # Filter for transactions with valid date and amount
    valid_current_transactions = [tx for tx in current_period_transactions if
                                  tx.date is not None and tx.amount is not None]
    if not valid_current_transactions:
        log.warning("No valid transactions (with date and amount) in current period for summary.")
        summary["total_transactions"] = len(current_period_transactions)  # Still report total attempted
        return summary

    summary["total_transactions"] = len(valid_current_transactions)
    valid_current_transactions.sort(key=lambda t: t.date)  # type: ignore
    summary["period_start_date"] = valid_current_transactions[0].date.isoformat() if valid_current_transactions[
        0].date else None  # type: ignore
    summary["period_end_date"] = valid_current_transactions[-1].date.isoformat() if valid_current_transactions[
        -1].date else None  # type: ignore

    # Core financial metrics
    current_metrics = _calculate_core_financial_metrics(valid_current_transactions)
    summary["total_income"] = str(current_metrics["total_income"].quantize(Decimal("0.01")))
    summary["total_spending"] = str(current_metrics["total_spending"].quantize(Decimal("0.01")))  # This is negative
    summary["net_flow_operational"] = str(current_metrics["net_flow_operational"].quantize(Decimal("0.01")))
    summary["spending_by_category"] = {k: str(v.quantize(Decimal("0.01"))) for k, v in
                                       current_metrics["spending_by_category"].items()}
    summary["income_by_category"] = {k: str(v.quantize(Decimal("0.01"))) for k, v in
                                     current_metrics["income_by_category"].items()}

    # Net change (all transactions, not just operational)
    net_change_total_dec = sum(tx.amount for tx in valid_current_transactions if tx.amount is not None)
    summary["net_change_total"] = str(net_change_total_dec.quantize(Decimal("0.01")))

    # Average and Median transaction amounts
    all_amounts_dec = [tx.amount for tx in valid_current_transactions if tx.amount is not None]
    if all_amounts_dec:
        summary["average_transaction_amount"] = str(
            (sum(all_amounts_dec) / len(all_amounts_dec)).quantize(Decimal("0.01")))
        sorted_amounts = sorted(all_amounts_dec)
        n = len(sorted_amounts);
        mid = n // 2
        if n % 2 == 1:
            summary["median_transaction_amount"] = str(sorted_amounts[mid].quantize(Decimal("0.01")))
        else:
            summary["median_transaction_amount"] = str(
                ((sorted_amounts[mid - 1] + sorted_amounts[mid]) / Decimal('2')).quantize(Decimal("0.01")))

    # Revenue breakdowns
    revenue_by_client_data = calculate_revenue_by_client(valid_current_transactions)
    summary["revenue_by_client"] = {client: str(rev.quantize(Decimal("0.01"))) for client, rev in
                                    revenue_by_client_data.items()}
    revenue_by_service_data = calculate_revenue_by_service(valid_current_transactions)
    summary["revenue_by_service"] = {service: str(rev.quantize(Decimal("0.01"))) for service, rev in
                                     revenue_by_service_data.items()}
    revenue_by_project_data = calculate_revenue_by_project(valid_current_transactions)
    summary["revenue_by_project"] = {project: str(rev.quantize(Decimal("0.01"))) for project, rev in
                                     revenue_by_project_data.items()}

    # Client rate and payment status
    summary["client_rate_analysis"] = calculate_client_rate_insights(valid_current_transactions)
    summary["payment_status_summary"] = calculate_payment_status_summary(valid_current_transactions,
                                                                         today_date=dt.date.today())

    # --- Populate Executive Summary ---
    exec_summary_data: Dict[str, Any] = {
        "total_income": summary["total_income"],
        "total_expenses": str(abs(Decimal(summary["total_spending"])).quantize(Decimal("0.01")))  # Positive for display
    }
    # Top client, service, project
    if revenue_by_client_data:
        top_client_list = sorted(revenue_by_client_data.items(), key=lambda item: item[1], reverse=True)
        if top_client_list: exec_summary_data["top_client_by_revenue"] = {"name": top_client_list[0][0], "amount": str(
            top_client_list[0][1].quantize(Decimal("0.01")))}
    if revenue_by_service_data:
        top_service_list = sorted(revenue_by_service_data.items(), key=lambda item: item[1], reverse=True)
        if top_service_list: exec_summary_data["top_service_by_revenue"] = {"name": top_service_list[0][0],
                                                                            "amount": str(
                                                                                top_service_list[0][1].quantize(
                                                                                    Decimal("0.01")))}
    if revenue_by_project_data:
        top_project_list = sorted(revenue_by_project_data.items(), key=lambda item: item[1], reverse=True)
        if top_project_list: exec_summary_data["top_project_by_revenue"] = {"name": top_project_list[0][0],
                                                                            "amount": str(
                                                                                top_project_list[0][1].quantize(
                                                                                    Decimal("0.01")))}
    # Best rate client
    if summary["client_rate_analysis"].get("best_average_rate_client"):
        exec_summary_data["best_rate_client"] = summary["client_rate_analysis"]["best_average_rate_client"]
    # Top expense category
    current_spending_by_cat_dec = {k: Decimal(v) for k, v in summary["spending_by_category"].items()}
    if current_spending_by_cat_dec:
        actual_expenses_categories = {cat: val for cat, val in current_spending_by_cat_dec.items() if
                                      val < 0}  # Ensure it's actual spending
        if actual_expenses_categories:
            # Sort by absolute value for "top" expense, but store original (negative) value for sorting
            top_expense_category_item = sorted(actual_expenses_categories.items(), key=lambda item: item[1])[
                0]  # Smallest (most negative) is largest expense
            exec_summary_data["top_expense_category"] = {"name": top_expense_category_item[0], "amount": str(
                abs(top_expense_category_item[1]).quantize(Decimal("0.01")))}
    # Payment status
    payment_summary_exec = summary["payment_status_summary"]
    if payment_summary_exec.get("total_outstanding", "0.00") != "0.00": exec_summary_data[
        "total_outstanding_invoices"] = payment_summary_exec["total_outstanding"]
    if payment_summary_exec.get("total_overdue", "0.00") != "0.00": exec_summary_data["total_overdue_invoices"] = \
    payment_summary_exec["total_overdue"]
    summary["executive_summary"] = exec_summary_data

    # --- Previous Period Comparison ---
    if previous_period_transactions:
        log.info("Calculating metrics for previous period...")
        valid_previous_transactions = [tx for tx in previous_period_transactions if
                                       tx.date is not None and tx.amount is not None]
        if valid_previous_transactions:
            prev_metrics = _calculate_core_financial_metrics(valid_previous_transactions)
            comparison_data: Dict[str, Any] = {
                "previous_total_income": str(prev_metrics["total_income"].quantize(Decimal("0.01"))),
                "previous_total_spending": str(prev_metrics["total_spending"].quantize(Decimal("0.01"))),  # Negative
                "previous_net_flow_operational": str(prev_metrics["net_flow_operational"].quantize(Decimal("0.01"))),
                "changes": {}
            }
            metrics_to_compare = {
                "total_income": (current_metrics["total_income"], prev_metrics["total_income"]),
                "total_spending": (current_metrics["total_spending"], prev_metrics["total_spending"]),
                # Compare negative values
                "net_flow_operational": (current_metrics["net_flow_operational"], prev_metrics["net_flow_operational"])
            }
            for key, (current_val_dec, prev_val_dec) in metrics_to_compare.items():
                change_dec = current_val_dec - prev_val_dec
                percent_change_val: Optional[float] = None
                if prev_val_dec != Decimal('0'):
                    # For spending, if prev_val is -100 and current is -50, change is 50.
                    # Percent change: (50 / abs(-100)) * 100 = 50% (a 50% decrease in spending magnitude)
                    percent_change_val = float(round((change_dec / abs(prev_val_dec)) * Decimal('100'), 1))
                elif current_val_dec != Decimal('0'):  # Previous was zero, current is not
                    percent_change_val = 100.0 if change_dec > 0 else -100.0

                comparison_data["changes"][key] = {
                    "current": str(current_val_dec.quantize(Decimal("0.01"))),
                    "previous": str(prev_val_dec.quantize(Decimal("0.01"))),
                    "change_amount": str(change_dec.quantize(Decimal("0.01"))),
                    "percent_change": percent_change_val
                }
            summary["previous_period_comparison"] = comparison_data
            log.info("Previous period comparison calculated.")
        else:
            log.warning("No valid transactions in previous period for comparison.")

    log.info("Full summary insights calculation finished.")
    return summary


# --- Monthly Spending Trends (calculate_monthly_spending_trends - as before) ---
# ... (This function can remain largely the same, ensure it uses the consistent Transaction class) ...
def calculate_monthly_spending_trends(transactions: List[Transaction]) -> Dict[str, Any]:
    log.debug(f"Calculating monthly trends for {len(transactions)} transactions.")
    trends: Dict[str, Any] = {
        "start_date": None, "end_date": None,
        "monthly_spending": {}, "trend_comparison": None
    }
    # ... (rest of the implementation as in your existing insights.py) ...
    # Ensure amounts are handled as Decimals and output as strings.
    return trends


# --- Recurring Transactions (identify_recurring_transactions - as before) ---
# ... (This function can also remain largely the same) ...
def identify_recurring_transactions(transactions: List[Transaction], min_occurrences: int = 3, days_tolerance: int = 7,
                                    amount_tolerance_percent: float = 15.0) -> Dict[str, List[Dict]]:
    log.debug(
        f"Identifying recurring transactions (min_occ:{min_occurrences}, day_tol:{days_tolerance}, amt_tol%:{amount_tolerance_percent}).")
    # ... (rest of the implementation as in your existing insights.py) ...
    return {"recurring_groups": []}  # Placeholder if not fully copied


if __name__ == "__main__":
    log.info("insights.py executed directly for testing.")
    test_user_id = "insights_test_user_vNext"


    # --- Test Monthly Revenue Trend ---
    # Mock the db_supabase functions for testing if db_supabase is not fully set up for direct run
    class MockDbSupabase:
        def get_revenue_for_past_n_months(self, user_id: str, num_months: int,
                                          data_context: Optional[str] = 'business') -> Dict[str, Decimal]:
            log.info(f"[MOCK DB] get_revenue_for_past_n_months called for user {user_id}, {num_months} months")
            # Simulate some data
            data = {}
            today = dt.date.today()
            first_of_last_month = (today.replace(day=1)) - relativedelta(months=1)
            for i in range(num_months):
                month_start = first_of_last_month - relativedelta(months=i)
                month_key = month_start.strftime("%Y-%m")
                data[month_key] = Decimal(str(1000 + (i * 150) + (hash(month_key) % 200)))  # Some varying data
            return dict(sorted(data.items()))

        def get_revenue_current_month_to_date(self, user_id: str, data_context: Optional[str] = 'business') -> Decimal:
            log.info(f"[MOCK DB] get_revenue_current_month_to_date called for user {user_id}")
            return Decimal("750.75")  # Simulate current MTD


    original_db_supabase = db_supabase  # Keep a reference to the original
    db_supabase = MockDbSupabase()  # type: ignore # Replace with mock for this test block

    print("\n--- Testing Monthly Revenue Trend ---")
    revenue_trend = calculate_monthly_revenue_trend(test_user_id, 6)
    import json  # For pretty printing

    print(json.dumps(revenue_trend, indent=2))

    db_supabase = original_db_supabase  # Restore original db_supabase

    # --- Test Full Summary Insights (with mock transactions if needed) ---
    # You can add more tests for calculate_summary_insights here,
    # ensuring the Transaction objects you create for testing have rate, quantity etc.
    print("\n--- Testing Full Summary Insights (Example) ---")
    sample_transactions = [
        Transaction(id=1, user_id=test_user_id, date=dt.date(2025, 5, 5), description="Client X Payment",
                    amount=Decimal("1500.00"), category="Income", client_name="Client X", rate=Decimal("100"),
                    quantity=Decimal("15")),
        Transaction(id=2, user_id=test_user_id, date=dt.date(2025, 5, 10), description="Software Subscription",
                    amount=Decimal("-75.00"), category="Software"),
        Transaction(id=3, user_id=test_user_id, date=dt.date(2025, 4, 5), description="Client X Payment (Prev)",
                    amount=Decimal("1200.00"), category="Income", client_name="Client X"),
        Transaction(id=4, user_id=test_user_id, date=dt.date(2025, 4, 10), description="Office Supplies (Prev)",
                    amount=Decimal("-50.00"), category="Office Supplies"),
    ]

    current_month_tx = [tx for tx in sample_transactions if tx.date and tx.date.year == 2025 and tx.date.month == 5]
    prev_month_tx = [tx for tx in sample_transactions if tx.date and tx.date.year == 2025 and tx.date.month == 4]

    summary_data = calculate_summary_insights(current_month_tx, prev_month_tx)
    print(json.dumps(summary_data, indent=2, default=str))  # Use default=str for Decimal/Date

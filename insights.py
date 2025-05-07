# insights.py

import logging
from collections import defaultdict, Counter
import datetime as dt
from dateutil.relativedelta import relativedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
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
try:
    from parser import Transaction

    log.info("Successfully imported Transaction class from parser module.")
except ImportError:
    log.error("Could not import Transaction class from parser.py. Defining a basic placeholder.")


    class Transaction:  # type: ignore
        def __init__(self, id: Optional[int], user_id: str, date: Optional[dt.date],
                     description: Optional[str], amount: Optional[Decimal], category: Optional[str],
                     client_name: Optional[str] = None, rate: Optional[Decimal] = None,
                     quantity: Optional[Decimal] = None, invoice_id: Optional[str] = None,
                     invoice_status: Optional[str] = None, date_paid: Optional[dt.date] = None,
                     project_id: Optional[str] = None,  # Added for completeness
                     transaction_origin: Optional[str] = None,
                     raw_description: Optional[str] = None
                     ):
            self.id = id;
            self.user_id = user_id;
            self.date = date;
            self.description = description
            self.amount = amount;
            self.category = category;
            self.client_name = client_name;
            self.rate = rate
            self.quantity = quantity;
            self.invoice_id = invoice_id;
            self.invoice_status = invoice_status
            self.date_paid = date_paid;
            self.project_id = project_id;
            self.transaction_origin = transaction_origin;
            self.raw_description = raw_description

        def to_dict(self) -> Dict[str, Any]: return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}


# --- Helper Function ---
def get_month_year_str(date_obj: Optional[dt.date]) -> Optional[str]:
    if date_obj is None: return None
    return date_obj.strftime('%Y-%m')


# --- Core Metrics Calculation ---
def _calculate_core_financial_metrics(transactions: List[Transaction]) -> Dict[str, Any]:  # Changed return type
    metrics: Dict[str, Any] = {  # Use Any for defaultdicts initially
        "total_income": Decimal('0'),
        "total_spending": Decimal('0'),
        "net_flow_operational": Decimal('0'),
        "spending_by_category": defaultdict(Decimal),
        "income_by_category": defaultdict(Decimal),
    }
    if not transactions:
        # Convert defaultdicts to dict for consistent return type even if empty
        metrics["spending_by_category"] = dict(metrics["spending_by_category"])
        metrics["income_by_category"] = dict(metrics["income_by_category"])
        return metrics

    operational_categories_to_exclude = ['Payments', 'Transfers', 'Ignore', 'Internal Transfer']

    for tx in transactions:
        if tx.amount is None: continue
        amount_dec = tx.amount
        category = tx.category if tx.category else 'Uncategorized'
        is_operational_exclusion = category in operational_categories_to_exclude

        if amount_dec > 0:
            metrics["income_by_category"][category] += amount_dec
            if not is_operational_exclusion:
                metrics["total_income"] += amount_dec
        elif amount_dec < 0:
            metrics["spending_by_category"][category] += amount_dec
            if not is_operational_exclusion:
                metrics["total_spending"] += amount_dec

    metrics["net_flow_operational"] = metrics["total_income"] + metrics["total_spending"]
    metrics["spending_by_category"] = dict(metrics["spending_by_category"])
    metrics["income_by_category"] = dict(metrics["income_by_category"])
    return metrics


# --- Revenue by Client ---
def calculate_revenue_by_client(transactions: List[Transaction]) -> Dict[str, Decimal]:
    revenue_by_client_dec = defaultdict(Decimal)
    if not transactions: return {}
    for tx in transactions:
        if tx.amount is not None and tx.amount > 0 and tx.client_name:
            client = tx.client_name.strip() if tx.client_name else "Unknown Client"
            revenue_by_client_dec[client] += tx.amount
    log.debug(f"Calculated revenue for {len(revenue_by_client_dec)} clients.")
    return dict(revenue_by_client_dec)


# --- Revenue by Service/Item ---
def calculate_revenue_by_service(transactions: List[Transaction]) -> Dict[str, Decimal]:
    revenue_by_service_dec = defaultdict(Decimal)
    if not transactions: return {}
    for tx in transactions:
        if tx.amount is not None and tx.amount > 0 and tx.description:
            service_item = tx.description.strip()
            revenue_by_service_dec[service_item] += tx.amount
    log.debug(f"Calculated revenue for {len(revenue_by_service_dec)} services/items.")
    return dict(revenue_by_service_dec)


# --- New Function: Revenue by Project ---
def calculate_revenue_by_project(transactions: List[Transaction]) -> Dict[str, Decimal]:
    """Calculates total revenue attributed to each project."""
    revenue_by_project_dec = defaultdict(Decimal)
    if not transactions:
        return {}

    for tx in transactions:
        if tx.amount is not None and tx.amount > 0 and tx.project_id:  # Check for project_id
            project = tx.project_id.strip() if tx.project_id else "Unspecified Project"
            revenue_by_project_dec[project] += tx.amount

    log.debug(f"Calculated revenue for {len(revenue_by_project_dec)} projects.")
    return dict(revenue_by_project_dec)


# --- Client Rate Analysis ---
def calculate_client_rate_insights(transactions: List[Transaction]) -> Dict[str, Any]:
    # ... (implementation as in insights_py_v7) ...
    client_rates_data: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"rates": [], "total_weighted_rate": Decimal(0), "total_quantity_for_avg": Decimal(0)})
    if not transactions: return {"rates_by_client": {}, "best_average_rate_client": None}
    for tx in transactions:
        if tx.client_name and tx.rate is not None and tx.rate > 0:
            client = tx.client_name.strip()
            client_rates_data[client]["rates"].append(tx.rate)
            quantity_for_weight = tx.quantity if tx.quantity is not None and tx.quantity > 0 else Decimal(1)
            client_rates_data[client]["total_weighted_rate"] += tx.rate * quantity_for_weight
            client_rates_data[client]["total_quantity_for_avg"] += quantity_for_weight
    processed_client_rates: Dict[str, Dict[str, str]] = {}
    best_avg_rate = Decimal("-1");
    best_avg_rate_client_name: Optional[str] = None
    for client, data in client_rates_data.items():
        if data["rates"]:
            avg_rate = (data["total_weighted_rate"] / data["total_quantity_for_avg"]) if data[
                                                                                             "total_quantity_for_avg"] > 0 else (
                        sum(data["rates"]) / len(data["rates"]))
            max_rate = max(data["rates"]);
            min_rate = min(data["rates"])
            processed_client_rates[client] = {
                "average_rate": str(avg_rate.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                "max_rate": str(max_rate.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                "min_rate": str(min_rate.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                "num_transactions_with_rate": str(len(data["rates"]))}
            if avg_rate > best_avg_rate: best_avg_rate = avg_rate; best_avg_rate_client_name = client
    best_client_details = None
    if best_avg_rate_client_name and best_avg_rate_client_name in processed_client_rates:
        best_client_details = {"name": best_avg_rate_client_name,
                               "average_rate": processed_client_rates[best_avg_rate_client_name]["average_rate"]}
    log.debug(f"Calculated rate insights for {len(processed_client_rates)} clients.")
    return {"rates_by_client": processed_client_rates, "best_average_rate_client": best_client_details}


# --- Payment Status Summary ---
def calculate_payment_status_summary(transactions: List[Transaction], today_date: Optional[dt.date] = None) -> Dict[
    str, Any]:
    # ... (implementation as in insights_py_v7) ...
    if today_date is None: today_date = dt.date.today()
    invoice_data: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"total_amount": Decimal(0), "status": None, "date_issued": None, "date_paid": None})
    for tx in transactions:
        if tx.invoice_id and tx.amount is not None:  # Ensure invoice_id is present
            inv_id = tx.invoice_id
            invoice_data[inv_id]["total_amount"] += tx.amount
            if invoice_data[inv_id]["status"] is None:
                invoice_data[inv_id]["status"] = tx.invoice_status.lower() if tx.invoice_status else "unknown"
                invoice_data[inv_id]["date_issued"] = tx.date
                invoice_data[inv_id]["date_paid"] = tx.date_paid
    status_summary: Dict[str, Decimal] = defaultdict(Decimal)
    total_outstanding = Decimal(0);
    total_overdue = Decimal(0)
    payment_terms_days = 30
    for inv_id, data in invoice_data.items():
        status = data["status"];
        amount = data["total_amount"];
        date_issued = data["date_issued"]
        status_summary[status] += amount
        if status in ["sent", "viewed", "partial"] and not data["date_paid"]:
            total_outstanding += amount
            if date_issued and (today_date - date_issued).days > payment_terms_days: total_overdue += amount
        elif status == "overdue":
            total_outstanding += amount;
            total_overdue += amount
    log.debug(f"Calculated payment status summary for {len(invoice_data)} unique invoices.")
    return {"by_status": {k: str(v.quantize(Decimal("0.01"))) for k, v in status_summary.items()},
            "total_outstanding": str(total_outstanding.quantize(Decimal("0.01"))),
            "total_overdue": str(total_overdue.quantize(Decimal("0.01")))}


# --- Main Summary Function ---
def calculate_summary_insights(
        current_period_transactions: List[Transaction],
        previous_period_transactions: Optional[List[Transaction]] = None,
        current_period_label: str = "Current Period",  # Not used yet, but for future
        previous_period_label: str = "Previous Period"  # Not used yet, but for future
) -> Dict[str, Any]:
    log.info(f"Calculating summary insights for current period ({len(current_period_transactions)} transactions).")
    if previous_period_transactions:
        log.info(f"Also calculating for previous period ({len(previous_period_transactions)} transactions).")

    summary = {
        "total_transactions": 0, "period_start_date": None, "period_end_date": None,
        "total_income": "0.00", "total_spending": "0.00",
        "net_flow_operational": "0.00",
        "spending_by_category": {}, "income_by_category": {},
        "revenue_by_client": {}, "revenue_by_service": {},
        "revenue_by_project": {},  # New field
        "client_rate_analysis": {}, "payment_status_summary": {},
        "average_transaction_amount": "0.00", "median_transaction_amount": "0.00",
        "executive_summary": {}, "previous_period_comparison": None
    }

    if not current_period_transactions:
        log.warning("No transactions provided for current period summary calculation.")
        return summary

    valid_current_transactions = [tx for tx in current_period_transactions if
                                  tx.date is not None and tx.amount is not None]
    if not valid_current_transactions:
        log.warning("No valid transactions in current period for summary.")
        summary["total_transactions"] = len(current_period_transactions)
        return summary

    summary["total_transactions"] = len(valid_current_transactions)
    valid_current_transactions.sort(key=lambda t: t.date)  # type: ignore
    summary["period_start_date"] = valid_current_transactions[0].date.isoformat() if valid_current_transactions[
        0].date else None  # type: ignore
    summary["period_end_date"] = valid_current_transactions[-1].date.isoformat() if valid_current_transactions[
        -1].date else None  # type: ignore

    current_metrics = _calculate_core_financial_metrics(valid_current_transactions)
    summary["total_income"] = str(current_metrics["total_income"].quantize(Decimal("0.01")))
    summary["total_spending"] = str(current_metrics["total_spending"].quantize(Decimal("0.01")))
    summary["net_flow_operational"] = str(current_metrics["net_flow_operational"].quantize(Decimal("0.01")))
    summary["spending_by_category"] = {k: str(v.quantize(Decimal("0.01"))) for k, v in
                                       current_metrics["spending_by_category"].items()}
    summary["income_by_category"] = {k: str(v.quantize(Decimal("0.01"))) for k, v in
                                     current_metrics["income_by_category"].items()}

    net_change_total_dec = sum(tx.amount for tx in valid_current_transactions if tx.amount is not None)
    summary["net_change_total"] = str(net_change_total_dec.quantize(Decimal("0.01")))

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

    revenue_by_client_data = calculate_revenue_by_client(valid_current_transactions)
    summary["revenue_by_client"] = {client: str(rev.quantize(Decimal("0.01"))) for client, rev in
                                    revenue_by_client_data.items()}

    revenue_by_service_data = calculate_revenue_by_service(valid_current_transactions)
    summary["revenue_by_service"] = {service: str(rev.quantize(Decimal("0.01"))) for service, rev in
                                     revenue_by_service_data.items()}

    # Calculate and add revenue by project
    revenue_by_project_data = calculate_revenue_by_project(valid_current_transactions)
    summary["revenue_by_project"] = {project: str(rev.quantize(Decimal("0.01"))) for project, rev in
                                     revenue_by_project_data.items()}

    summary["client_rate_analysis"] = calculate_client_rate_insights(valid_current_transactions)
    summary["payment_status_summary"] = calculate_payment_status_summary(valid_current_transactions,
                                                                         today_date=dt.date.today())

    # --- Populate Executive Summary ---
    exec_summary_data: Dict[str, Any] = {
        "total_income": summary["total_income"],
        "total_expenses": summary["total_spending"]
    }
    # ... (executive summary population as in insights_py_v7, adding top project)
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

    if revenue_by_project_data:  # New for executive summary
        top_project_list = sorted(revenue_by_project_data.items(), key=lambda item: item[1], reverse=True)
        if top_project_list: exec_summary_data["top_project_by_revenue"] = {"name": top_project_list[0][0],
                                                                            "amount": str(
                                                                                top_project_list[0][1].quantize(
                                                                                    Decimal("0.01")))}

    if summary["client_rate_analysis"].get("best_average_rate_client"):
        exec_summary_data["best_rate_client"] = summary["client_rate_analysis"]["best_average_rate_client"]

    current_spending_by_cat_dec = {k: Decimal(v) for k, v in summary["spending_by_category"].items()}
    if current_spending_by_cat_dec:
        actual_expenses_categories = {cat: val for cat, val in current_spending_by_cat_dec.items() if val < 0}
        if actual_expenses_categories:
            top_expense_category_item = sorted(actual_expenses_categories.items(), key=lambda item: item[1])[0]
            exec_summary_data["top_expense_category"] = {"name": top_expense_category_item[0], "amount": str(
                abs(top_expense_category_item[1]).quantize(Decimal("0.01")))}

    payment_summary_exec = summary["payment_status_summary"]
    if payment_summary_exec.get("total_outstanding", "0.00") != "0.00":
        exec_summary_data["total_outstanding_invoices"] = payment_summary_exec["total_outstanding"]
    if payment_summary_exec.get("total_overdue", "0.00") != "0.00":
        exec_summary_data["total_overdue_invoices"] = payment_summary_exec["total_overdue"]
    summary["executive_summary"] = exec_summary_data

    # --- Previous Period Comparison ---
    if previous_period_transactions:
        # ... (implementation as in insights_py_v7) ...
        log.info("Calculating metrics for previous period...")
        valid_previous_transactions = [tx for tx in previous_period_transactions if
                                       tx.date is not None and tx.amount is not None]
        if valid_previous_transactions:
            prev_metrics = _calculate_core_financial_metrics(valid_previous_transactions)
            comparison_data: Dict[str, Any] = {
                "previous_total_income": str(prev_metrics["total_income"].quantize(Decimal("0.01"))),
                "previous_total_spending": str(prev_metrics["total_spending"].quantize(Decimal("0.01"))),
                "previous_net_flow_operational": str(prev_metrics["net_flow_operational"].quantize(Decimal("0.01"))),
                "changes": {}}
            metrics_to_compare = {"total_income": (current_metrics["total_income"], prev_metrics["total_income"]),
                                  "total_spending": (current_metrics["total_spending"], prev_metrics["total_spending"]),
                                  "net_flow_operational": (
                                  current_metrics["net_flow_operational"], prev_metrics["net_flow_operational"])}
            for key, (current_val, prev_val) in metrics_to_compare.items():
                change = current_val - prev_val;
                percent_change = None
                if prev_val != 0:
                    percent_change = round((change / abs(prev_val)) * 100, 1)
                elif current_val != 0:
                    percent_change = 100.0 if current_val > 0 else -100.0 if current_val < 0 else 0.0
                comparison_data["changes"][key] = {"current": str(current_val.quantize(Decimal("0.01"))),
                                                   "previous": str(prev_val.quantize(Decimal("0.01"))),
                                                   "change_amount": str(change.quantize(Decimal("0.01"))),
                                                   "percent_change": percent_change}
            summary["previous_period_comparison"] = comparison_data
            log.info("Previous period comparison calculated.")
        else:
            log.warning("No valid transactions in previous period for comparison.")

    log.info("Full summary insights calculation finished.")
    return summary


# --- Monthly Spending Trends (remains the same as insights_py_v7) ---
def calculate_monthly_spending_trends(transactions: List[Transaction]) -> Dict[str, Any]:
    # ... (implementation as in insights_py_v7) ...
    log.debug(f"Calculating monthly trends for {len(transactions)} transactions.")
    trends: Dict[str, Any] = {
        "start_date": None, "end_date": None,
        "monthly_spending": {}, "trend_comparison": None
    }
    if not transactions:
        log.warning("No transactions for trend calculation.")
        return trends
    valid_dates = sorted([tx.date for tx in transactions if tx.date is not None])
    if not valid_dates:
        log.warning("No valid dates in transactions for trend calculation.")
        return trends
    trends["start_date"] = valid_dates[0].isoformat()
    trends["end_date"] = valid_dates[-1].isoformat()
    monthly_data_dec = defaultdict(lambda: defaultdict(Decimal))
    operational_spending_exclusions = ['Payments', 'Transfers', 'Ignore', 'Income', 'Internal Transfer',
                                       'Credit Card Payment']
    for tx in transactions:
        if tx.date is None or tx.amount is None or tx.amount >= 0: continue
        if tx.category in operational_spending_exclusions: continue
        month_year_key = get_month_year_str(tx.date)
        if month_year_key is None: continue
        category = tx.category if tx.category else 'Uncategorized'
        monthly_data_dec[month_year_key][category] += abs(tx.amount)
        monthly_data_dec[month_year_key]['__total__'] += abs(tx.amount)
    trends["monthly_spending"] = {
        month: {cat: str(val.quantize(Decimal("0.01"))) for cat, val in data.items()}
        for month, data in monthly_data_dec.items()
    }
    sorted_months = sorted(monthly_data_dec.keys())
    if len(sorted_months) >= 2:
        current_month_key = sorted_months[-1];
        previous_month_key = sorted_months[-2]
        current_data = monthly_data_dec[current_month_key];
        previous_data = monthly_data_dec[previous_month_key]
        comparison_details = {}
        all_categories_for_trend = set(current_data.keys()) | set(previous_data.keys())
        all_categories_for_trend.discard('__total__')
        for category in sorted(list(all_categories_for_trend)):
            current_amount = current_data.get(category, Decimal('0'));
            previous_amount = previous_data.get(category, Decimal('0'))
            change = current_amount - previous_amount
            percent_change = float((change / abs(previous_amount)) * 100) if previous_amount != 0 else (
                100.0 if change > 0 else (-100.0 if change < 0 else 0.0))
            comparison_details[category] = {"current_amount": str(current_amount.quantize(Decimal("0.01"))),
                                            "previous_amount": str(previous_amount.quantize(Decimal("0.01"))),
                                            "change": str(change.quantize(Decimal("0.01"))),
                                            "percent_change": round(percent_change,
                                                                    1) if percent_change is not None else None, }
        total_current = current_data.get('__total__', Decimal('0'));
        total_previous = previous_data.get('__total__', Decimal('0'))
        total_change = total_current - total_previous
        total_percent_change = float((total_change / abs(total_previous)) * 100) if total_previous != 0 else (
            100.0 if total_change > 0 else (-100.0 if total_change < 0 else 0.0))
        trends["trend_comparison"] = {"current_month_str": current_month_key, "previous_month_str": previous_month_key,
                                      "total_current_spending": str(total_current.quantize(Decimal("0.01"))),
                                      "total_previous_spending": str(total_previous.quantize(Decimal("0.01"))),
                                      "total_change": str(total_change.quantize(Decimal("0.01"))),
                                      "total_percent_change": round(total_percent_change,
                                                                    1) if total_percent_change is not None else None,
                                      "comparison": comparison_details}
    log.debug("Monthly spending trend calculation finished.")
    return trends


# --- Recurring Transactions (remains the same as insights_py_v7) ---
def identify_recurring_transactions(transactions: List[Transaction], min_occurrences: int = 3, days_tolerance: int = 7,
                                    amount_tolerance_percent: float = 15.0) -> Dict[str, List[Dict]]:
    # ... (implementation as in insights_py_v7) ...
    log.debug(
        f"Identifying recurring transactions (min_occ:{min_occurrences}, day_tol:{days_tolerance}, amt_tol%:{amount_tolerance_percent}).")
    if not transactions: return {"recurring_groups": []}
    grouped_by_desc: Dict[str, List[Transaction]] = defaultdict(list)
    for tx in transactions:
        if tx.description and tx.date and tx.amount is not None:
            clean_desc = tx.description.lower().strip()
            grouped_by_desc[clean_desc].append(tx)
    potential_recurring_groups: List[Dict] = []
    for desc_key, group_txs in grouped_by_desc.items():
        if len(group_txs) < min_occurrences: continue
        group_txs.sort(key=lambda t: t.date)  # type: ignore
        amount_clusters: Dict[Decimal, List[Transaction]] = defaultdict(list)
        for tx in group_txs:
            matched_to_cluster = False
            for base_amount in list(amount_clusters.keys()):
                tolerance_value = abs(base_amount * (Decimal(str(amount_tolerance_percent)) / Decimal('100')))
                if abs(tx.amount - base_amount) <= tolerance_value:  # type: ignore
                    amount_clusters[base_amount].append(tx);
                    matched_to_cluster = True;
                    break
            if not matched_to_cluster: amount_clusters[tx.amount].append(tx)  # type: ignore
        for base_amt, clustered_txs in amount_clusters.items():
            if len(clustered_txs) < min_occurrences: continue
            intervals_days: List[int] = []
            for i in range(len(clustered_txs) - 1):
                delta = clustered_txs[i + 1].date - clustered_txs[i].date  # type: ignore
                intervals_days.append(delta.days)
            if not intervals_days: continue
            interval_counts = Counter(intervals_days)
            most_common_raw_interval, _ = interval_counts.most_common(1)[0] if interval_counts else (None, 0)
            if most_common_raw_interval is None: continue
            consistent_intervals: List[int] = []
            for interval in intervals_days:
                if abs(interval - most_common_raw_interval) <= days_tolerance: consistent_intervals.append(interval)
            if len(consistent_intervals) >= min_occurrences - 1:
                avg_consistent_interval = round(sum(consistent_intervals) / len(
                    consistent_intervals)) if consistent_intervals else most_common_raw_interval
                avg_amount_for_group = sum(t.amount for t in clustered_txs) / len(clustered_txs)  # type: ignore
                potential_recurring_groups.append({"description": desc_key, "category": clustered_txs[0].category,
                                                   "average_amount": str(
                                                       avg_amount_for_group.quantize(Decimal("0.01"))),
                                                   "count": len(clustered_txs),
                                                   "interval_days": avg_consistent_interval,
                                                   "transactions": [t.to_dict() for t in clustered_txs]})
    log.debug(f"Identified {len(potential_recurring_groups)} potential recurring groups.")
    potential_recurring_groups.sort(key=lambda g: (g['count'], abs(Decimal(g['average_amount']))), reverse=True)
    return {"recurring_groups": potential_recurring_groups}


if __name__ == "__main__":
    log.info("insights.py executed directly for testing.")
    test_user_id = "insights_test_user"

    test_tx_projects = [
        Transaction(id=1, user_id=test_user_id, date=dt.date(2025, 5, 5), description="Phase 1 Dev",
                    amount=Decimal("1500.00"), category="Service", client_name="Client X", project_id="Project Alpha"),
        Transaction(id=2, user_id=test_user_id, date=dt.date(2025, 5, 10), description="Consulting",
                    amount=Decimal("500.00"), category="Service", client_name="Client Y", project_id="Project Beta"),
        Transaction(id=3, user_id=test_user_id, date=dt.date(2025, 5, 12), description="Phase 2 Dev",
                    amount=Decimal("2000.00"), category="Service", client_name="Client X", project_id="Project Alpha"),
        Transaction(id=4, user_id=test_user_id, date=dt.date(2025, 5, 18), description="Support Retainer",
                    amount=Decimal("300.00"), category="Service", client_name="Client Z", project_id=None),
        # No project
        Transaction(id=5, user_id=test_user_id, date=dt.date(2025, 5, 20), description="Design Work",
                    amount=Decimal("750.00"), category="Service", client_name="Client Y", project_id="Project Beta"),
    ]

    print("\n--- Testing Revenue by Project ---")
    project_revenue = calculate_revenue_by_project(test_tx_projects)
    print(json.dumps({k: str(v) for k, v in project_revenue.items()}, indent=2))

    print("\n--- Testing Full Summary Insights (with Project Revenue) ---")
    summary_with_projects = calculate_summary_insights(test_tx_projects)
    print(json.dumps(summary_with_projects, indent=2))


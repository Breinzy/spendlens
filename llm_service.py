import google.generativeai as genai
import os
import logging
from decimal import Decimal, InvalidOperation  # Added InvalidOperation
import datetime as dt
from collections import Counter
from typing import Dict, Any, List, Optional, Tuple
from dotenv import load_dotenv
import random
import json

load_dotenv()

log = logging.getLogger('llm_service')
log.setLevel(logging.INFO)
if not log.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)

model = None
is_configured = False

try:
    GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
    if not GOOGLE_API_KEY:
        log.warning("GOOGLE_API_KEY not found in environment variables during initial load.")
    else:
        log.info(f"Initial load: Found GOOGLE_API_KEY starting with: {GOOGLE_API_KEY[:4]}...")
        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
        is_configured = True
        log.info(f"Gemini API configured successfully during initial load with model 'gemini-1.5-flash'.")
except ImportError:
    log.error("google.generativeai library not found. Please install it: pip install google-generativeai")
except Exception as e:
    log.error(f"Initial Gemini configuration failed: {e}", exc_info=True)


# Transaction class definition within llm_service
# This should align with the fields passed from insights_router.py
class Transaction:
    id: Optional[int] = None  # Changed to Optional[int] to match db_tx.id
    date: Optional[dt.date] = None
    description: Optional[str] = None
    amount: Optional[Decimal] = None
    category: Optional[str] = None
    transaction_type: Optional[str] = None
    source_account_type: Optional[str] = None
    source_filename: Optional[str] = None
    raw_description: Optional[str] = None

    def __init__(self, id: Optional[int] = None, date: Optional[dt.date] = None, description: Optional[str] = None,
                 amount: Optional[Decimal] = None, category: Optional[str] = None,
                 transaction_type: Optional[str] = None, source_account_type: Optional[str] = None,
                 source_filename: Optional[str] = None, raw_description: Optional[str] = None):
        self.id = id
        self.date = date
        self.description = description
        self.amount = amount
        self.category = category
        self.transaction_type = transaction_type
        self.source_account_type = source_account_type
        self.source_filename = source_filename
        self.raw_description = raw_description if raw_description else description


def format_transactions_for_qa(
        transactions: List[Transaction],
        start_date_str: Optional[str] = None,
        end_date_str: Optional[str] = None
) -> str:
    if not transactions:
        return "No transaction data provided for the specified period."

    limit_note = f"\n(Displaying all {len(transactions)} transactions provided for the period)"

    if start_date_str and end_date_str:
        header = f"Transaction List (Period: {start_date_str} to {end_date_str}):"
    # ... (rest of the function as before) ...
    else:
        header = "Transaction List (Full period provided):"

    formatted_list = [header]
    for tx in transactions:
        date_str = tx.date.isoformat() if tx.date else 'N/A'
        desc = tx.description or 'N/A'
        # Ensure amount is Decimal before formatting
        amount_val = tx.amount if isinstance(tx.amount, Decimal) else Decimal(
            str(tx.amount)) if tx.amount is not None else Decimal('0')
        amount_str = f"{amount_val:.2f}"
        category = tx.category or 'N/A'
        formatted_list.append(f"- {date_str}: {desc} ({category}) | Amount: {amount_str}")

    formatted_list.append(limit_note)
    return "\n".join(formatted_list)


def format_summary_for_qa(summary_data: Optional[Dict[str, Any]], start_date_str: Optional[str],
                          end_date_str: Optional[str]) -> str:
    if not summary_data:
        return "No summary statistics calculated for the period."

    period_str = "Overall"
    if start_date_str and end_date_str:
        period_str = f"Period: {start_date_str} to {end_date_str}"
    # ... (rest of the function as before) ...
    else:
        period_str = "Full Period Provided"

    formatted_string = f"Summary Statistics ({period_str}):\n"

    # Helper to safely convert to Decimal and format
    def safe_format_decimal(key: str, default_val: str = '0') -> str:
        val_str = summary_data.get(key, default_val)
        try:
            # Values from adapted_summary_for_llm are already strings representing numbers
            return f"{Decimal(val_str):.2f}"
        except (InvalidOperation, TypeError):
            log.warning(f"Could not convert summary value for '{key}' to Decimal: {val_str}")
            return f"{Decimal(default_val):.2f}"

    formatted_string += f"- Total Operational Income: ${safe_format_decimal('operational_income')}\n"
    # operational_spending is negative, display as positive spending
    op_spending_str = summary_data.get('operational_spending', '0')
    try:
        op_spending_dec = Decimal(op_spending_str)
        formatted_string += f"- Total Operational Spending: ${abs(op_spending_dec):.2f}\n"
    except (InvalidOperation, TypeError):
        formatted_string += f"- Total Operational Spending: $0.00\n"
        log.warning(f"Could not convert operational_spending to Decimal: {op_spending_str}")

    formatted_string += f"- Net Operational Flow: ${safe_format_decimal('net_operational_flow')}\n"

    net_spending = summary_data.get('net_spending_by_category', {})  # This is Dict[str, str]
    if net_spending and isinstance(net_spending, dict):
        formatted_string += "- Top Net Spending Categories (absolute amounts):\n"
        # Sort items by Decimal value (which are positive strings), descending
        try:
            top_spending = sorted(
                net_spending.items(),
                key=lambda item: Decimal(item[1] if item[1] is not None else '0'),  # item[1] is string amount
                reverse=True
            )[:3]
            for cat, amount_str in top_spending:
                formatted_string += f"  - {cat}: ${Decimal(amount_str):.2f}\n"  # amount_str is already positive
        except (InvalidOperation, TypeError) as e:
            log.warning(f"Error processing net_spending_by_category for LLM: {e}")
            formatted_string += "  - (Error processing spending categories)\n"

    formatted_string += f"- Total Transactions Analyzed: {summary_data.get('transaction_count', 0)}\n"
    return formatted_string


def format_data_for_llm(summary_data, trends_data, start_date_str, end_date_str):
    # ... (This function is for the older summary generation, likely okay as is) ...
    # ... (but ensure it handles Decimal conversion from string if summary_data structure changed) ...
    prompt_lines = [
        f"Financial Analysis Report ({start_date_str} to {end_date_str})\n",
        "--- Overall Summary ---"
    ]
    prompt_lines.append(f"Total Income: ${Decimal(summary_data.get('total_income', '0')):.2f}")
    prompt_lines.append(
        f"Total Operational Spending: ${abs(Decimal(summary_data.get('total_operational_spending', '0'))):.2f}")
    # ... (rest of this function as before) ...
    return "\n".join(prompt_lines)


def generate_financial_summary(summary_data: Dict[str, Any], trends_data: Dict[str, Any], start_date_str: str,
                               end_date_str: str) -> str:
    # ... (This function remains largely the same, used for a different purpose than AI Q&A) ...
    global model, is_configured
    if not is_configured:  # Re-check config
        # ... (config logic as before) ...
        pass
    if model is None: return "Error: LLM model is not available."

    # Ensure summary_data fields are converted to Decimal for format_data_for_llm if they are strings
    # This depends on what calculate_summary_insights now returns vs what format_data_for_llm expects
    # For now, assuming format_data_for_llm handles string inputs or they are already Decimal
    formatted_data = format_data_for_llm(summary_data, trends_data, start_date_str, end_date_str)
    # ... (rest of prompt and API call as before) ...
    return "Error: Could not generate summary due to an API error."  # Fallback


def answer_financial_question(
        question: str,
        transactions: List[Transaction],  # Expects list of llm_service.Transaction
        summary_data: Optional[Dict[str, Any]],  # Expects the adapted summary
        start_date_str: Optional[str] = None,
        end_date_str: Optional[str] = None,
        pre_calculated_result: Optional[Decimal] = None
) -> Tuple[str, str]:
    # ... (Configuration check for model as before) ...
    global model, is_configured
    if not is_configured or model is None:
        log.error("LLM not configured. Cannot answer question.")
        return "Error: LLM model is not configured.", "error"

    current_date = dt.date.today()
    current_date_str = current_date.isoformat()

    details_requested = any(detail_word in question.lower() for detail_word in
                            ["show transaction", "list transaction", "details", "breakdown"])

    formatted_transactions_context = ""
    include_tx_list = pre_calculated_result is None or details_requested

    if include_tx_list:
        formatted_transactions_context = format_transactions_for_qa(transactions, start_date_str, end_date_str)
    else:
        formatted_transactions_context = "(Transaction list omitted as pre-calculated result is provided and details were not explicitly requested)"

    formatted_summary_context = format_summary_for_qa(summary_data, start_date_str, end_date_str)
    # ... (rest of the prompt construction and API call as before, using the formatted contexts) ...
    # Ensure the prompt uses formatted_transactions_context and formatted_summary_context

    prompt_lines = [
        "You are SpendLens, a helpful financial assistant.",
        f"The current date is: {current_date_str}. Use this date ONLY to understand relative time references in the user's question (like 'this year', 'last month').",
        # ... (rest of prompt lines from your existing llm_service.py) ...
        "\nAvailable Data:",
        f"1. Summary Statistics:\n{formatted_summary_context}",  # Use the formatted summary
        f"\n2. Transaction List (only included if no pre-calc or details requested):\n{formatted_transactions_context}",
        # Use the formatted transactions
        # ... (rest of instructions and question) ...
    ]
    prompt = "\n".join(prompt_lines)
    log.debug(f"Final Q&A Prompt (first 300 chars):\n{prompt[:300]}")

    try:
        response = model.generate_content(prompt)
        # ... (response handling as before) ...
        if hasattr(response, 'text') and response.text:
            # ... (success/refusal logic) ...
            return response.text.strip(), "success"  # Example
        # ... (other error/block handling) ...
        return "Error: Could not get answer due to unexpected API response format.", "error"

    except Exception as e:
        log.error(f"Error calling Gemini API for Q&A: {e}", exc_info=True)
        return f"Error: Could not get answer due to an API error ({type(e).__name__}).", "error"


def suggest_categories_for_transactions(
        transactions_to_categorize: List[Transaction],  # Expects llm_service.Transaction
        valid_categories: List[str],
        existing_rules: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    # ... (This function should be okay if transactions_to_categorize are llm_service.Transaction) ...
    # ... (Ensure amount is handled correctly if it's Decimal) ...
    global model, is_configured
    if not is_configured or model is None: return {}
    if not transactions_to_categorize or not valid_categories: return {}
    # ... (rest of the function as before, ensuring Decimal amounts are handled for prompt) ...
    return {}


if __name__ == '__main__':
    log.info("llm_service.py executed directly for testing.")
    # ... (your existing test block) ...

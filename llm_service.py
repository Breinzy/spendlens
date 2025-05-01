import google.generativeai as genai
import os
import logging
from decimal import Decimal
import datetime as dt
from collections import Counter
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [LLM_SERVICE] %(message)s')

# --- Global variable for the model ---
model = None
is_configured = False

# --- Attempt initial configuration ---
try:
    GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
    if not GOOGLE_API_KEY: logging.warning("GOOGLE_API_KEY not found during initial load.")
    else:
        logging.info(f"Initial load: Found GOOGLE_API_KEY starting with: {GOOGLE_API_KEY[:4]}...")
        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
        is_configured = True; logging.info("Gemini API configured successfully during initial load.")
except Exception as e: logging.error(f"Initial Gemini configuration failed: {e}", exc_info=True)

# Import Transaction class definition from parser
try: from parser import Transaction
except ImportError:
    logging.warning("Could not import Transaction from parser for LLM Q&A.")
    class Transaction: pass

# --- Change: Update formatting note ---
def format_transactions_for_qa(
    transactions: List[Transaction],
    start_date_str: Optional[str] = None,
    end_date_str: Optional[str] = None
    ) -> str:
    """Formats a list of transactions into a concise string for LLM Q&A prompts."""
    if not transactions:
        return "No transaction data provided for the specified period."

    # No longer limiting by max_tx here, app.py handles date range
    limited_transactions = transactions
    limit_note = f"\n(Displaying all {len(transactions)} transactions provided for the period)"

    if start_date_str and end_date_str: header = f"Transaction List (Period: {start_date_str} to {end_date_str}):"
    elif start_date_str: header = f"Transaction List (Period: From {start_date_str} onwards):"
    elif end_date_str: header = f"Transaction List (Period: Up to {end_date_str}):"
    # Change: Update default header text
    else: header = "Transaction List (Defaulting to last ~2 years):"

    formatted_list = [header]
    for tx in limited_transactions:
        date_str = tx.date.isoformat() if hasattr(tx, 'date') and isinstance(tx.date, dt.date) else 'N/A'
        desc = getattr(tx, 'description', 'N/A')
        amount = getattr(tx, 'amount', Decimal('0'))
        amount_str = f"{amount:.2f}" if isinstance(amount, Decimal) else 'N/A'
        category = getattr(tx, 'category', 'N/A')
        formatted_list.append(f"- {date_str}: {desc} ({category}) | Amount: {amount_str}")

    formatted_list.append(limit_note)
    return "\n".join(formatted_list)
# --- End Change ---


def format_summary_for_qa(summary_data: Optional[Dict[str, Any]], start_date_str: Optional[str], end_date_str: Optional[str]) -> str:
    # ... (format_summary_for_qa remains the same) ...
    if not summary_data: return "No summary statistics calculated for the period."
    period_str = "Overall"
    if start_date_str and end_date_str: period_str = f"Period: {start_date_str} to {end_date_str}"
    elif start_date_str: period_str = f"Period: From {start_date_str}"
    elif end_date_str: period_str = f"Period: Up to {end_date_str}"
    else: period_str = "Last ~2 Years (Default)" # Clarify default period
    formatted_string = f"Summary Statistics ({period_str}):\n"
    formatted_string += f"- Total Operational Income: ${Decimal(summary_data.get('operational_income', 0)):.2f}\n"
    formatted_string += f"- Total Operational Spending: ${Decimal(summary_data.get('operational_spending', 0)):.2f}\n"
    formatted_string += f"- Net Operational Flow: ${Decimal(summary_data.get('net_operational_flow', 0)):.2f}\n"
    net_spending = summary_data.get('net_spending_by_category', {})
    if net_spending:
         formatted_string += "- Top Net Spending Categories:\n"
         top_spending = sorted(net_spending.items(), key=lambda item: Decimal(item[1]), reverse=True)[:3]
         for cat, amount in top_spending: formatted_string += f"  - {cat}: ${Decimal(amount):.2f}\n"
    formatted_string += f"- Total Transactions Analyzed: {summary_data.get('transaction_count', 0)}\n"
    return formatted_string


def generate_financial_summary(summary_data: Dict[str, Any], trends_data: Dict[str, Any], start_date_str: str, end_date_str: str) -> str:
    # ... (generate_financial_summary remains the same) ...
    global model, is_configured
    if not is_configured:
        logging.warning("Model not configured initially, attempting configuration...");
        try:
            API_KEY = os.environ.get('GOOGLE_API_KEY')
            if not API_KEY: logging.error("GOOGLE_API_KEY still not found."); return "Error: LLM model could not be configured - API key missing."
            else: logging.info(f"Found GOOGLE_API_KEY starting with: {API_KEY[:4]}... in function."); genai.configure(api_key=API_KEY); model = genai.GenerativeModel('gemini-1.5-flash'); is_configured = True; logging.info("Gemini API configured successfully within function.")
        except Exception as e: logging.error(f"Gemini configuration failed within function: {e}", exc_info=True); return f"Error: LLM model configuration failed ({type(e).__name__})."
    if model is None: logging.error("generate_financial_summary called but model is None."); return "Error: LLM model is not available."
    formatted_data = format_data_for_llm(summary_data, trends_data, start_date_str, end_date_str)
    prompt = f"""
    You are SpendLens, a friendly financial assistant. Your goal is to provide clear, simple insights.
    Analyze the following financial data for the specified period. Provide a brief summary (2-3 sentences) using simple words.
    Highlight the main points like net flow, biggest spending areas, and major spending changes if available. Keep the tone helpful. Avoid jargon.
    Financial Data: {formatted_data} Simple Summary: """
    logging.info("Generating financial summary with Gemini...")
    try:
        response = model.generate_content(prompt)
        if hasattr(response, 'text'): generated_text = response.text.strip(); logging.info("Successfully generated summary."); return generated_text
        else: logging.error(f"Gemini response unexpected format: {response}"); return "Error: Could not generate summary due to unexpected API response."
    except Exception as e: logging.error(f"Error calling Gemini API: {e}", exc_info=True); return f"Error: Could not generate summary due to an API error ({type(e).__name__})."


# --- Change: Update Q&A Prompt Context ---
def answer_financial_question(
    question: str,
    transactions: List[Transaction],
    summary_data: Optional[Dict[str, Any]],
    start_date_str: Optional[str] = None,
    end_date_str: Optional[str] = None
    ) -> str:
    """Uses the Gemini API to answer a specific financial question."""
    global model, is_configured
    # Ensure model is configured
    if not is_configured:
        logging.warning("Model not configured initially, attempting configuration for Q&A...")
        try:
            API_KEY = os.environ.get('GOOGLE_API_KEY')
            if not API_KEY: logging.error("GOOGLE_API_KEY still not found."); return "Error: LLM model could not be configured - API key missing."
            else: logging.info(f"Found GOOGLE_API_KEY starting with: {API_KEY[:4]}... in Q&A function."); genai.configure(api_key=API_KEY); model = genai.GenerativeModel('gemini-1.5-flash'); is_configured = True; logging.info("Gemini API configured successfully within Q&A function.")
        except Exception as e: logging.error(f"Gemini configuration failed within Q&A function: {e}", exc_info=True); return f"Error: LLM model configuration failed ({type(e).__name__})."
    if model is None: logging.error("answer_financial_question called but model is None."); return "Error: LLM model is not available."

    formatted_summary = format_summary_for_qa(summary_data, start_date_str, end_date_str)
    # Pass all relevant transactions
    formatted_transactions = format_transactions_for_qa(transactions, start_date_str, end_date_str)

    # Update data scope info based on dates
    data_scope_info = "the last 2 years of available data (default)"
    if start_date_str and end_date_str: data_scope_info = f"data between {start_date_str} and {end_date_str}"
    elif start_date_str: data_scope_info = f"data since {start_date_str}"
    elif end_date_str: data_scope_info = f"data up to {end_date_str}"

    prompt = f"""
    You are SpendLens, a helpful financial assistant.
    Answer the following user question based *only* on the provided data ({data_scope_info}).

    Available Data:
    1. Summary Statistics: Use these first for questions about totals, averages, or overall figures for the period.
    {formatted_summary}

    2. Full Transaction List: Use this if the question asks for specific details (like dates, vendor names, individual amounts) not in the summary, or if you need to verify calculations *across the entire period provided*.
    {formatted_transactions}

    Instructions:
    - Prioritize using the Summary Statistics for calculations (totals, averages).
    - Refer to the Full Transaction List only if necessary for specifics or verification.
    - If the answer cannot be determined from the provided data (summary or list), clearly state that the information is not available in the data provided for the specified period.
    - Be concise and directly answer the question using simple language.

    User Question: {question}

    Answer:
    """

    logging.info(f"Answering question with Gemini: '{question}' (Data scope: {data_scope_info})")
    try:
        response = model.generate_content(prompt)
        if hasattr(response, 'text'):
             generated_text = response.text.strip(); logging.info("Successfully generated answer."); return generated_text
        else:
             if not response.candidates: block_reason = "Unknown";
             # Corrected indentation
             if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                 block_reason = response.prompt_feedback.block_reason  # Indent this line             logging.error(f"Gemini Q&A response unexpected format. Response: {response}"); return "Error: Unexpected API response format."
    except Exception as e:
        logging.error(f"Error calling Gemini API for Q&A: {e}", exc_info=True)
        return f"Error: Could not get answer due to an API error ({type(e).__name__})."
# --- End Change ---


# (Testing block remains the same)
if __name__ == '__main__':
    # ... (rest of testing code) ...
    dummy_summary = {"operational_income": Decimal('2500.00'), "operational_spending": Decimal('1800.50'), "net_operational_flow": Decimal('699.50'), "net_spending_by_category": {"Groceries": "350.20", "Food": "250.10", "Shopping": "400.00"}, "transaction_count": 25}
    dummy_trends = {"current_month": "2025-04", "previous_month": "2025-03", "trends": [{"category": "Shopping", "change_amount": "150.00", "change_percent": 60.0},{"category": "Food", "change_amount": "-50.00", "change_percent": -16.7},{"category": "Groceries", "change_amount": "10.00", "change_percent": 2.9},]}
    start_test = "2025-04-01"; end_test = "2025-04-30"
    print("--- Testing LLM Summary Generation ---"); summary_text = generate_financial_summary(dummy_summary, dummy_trends, start_test, end_test); print("\nGenerated Summary:"); print(summary_text)
    print("\n--- Testing LLM Q&A ---")
    qa_test_transactions = [ Transaction(id=1, date=dt.date(2025, 4, 5), description="Grocery Mart", amount=Decimal("-55.00"), category="Groceries"), Transaction(id=2, date=dt.date(2025, 4, 10), description="Gas Station #1", amount=Decimal("-40.00"), category="Gas"), Transaction(id=3, date=dt.date(2025, 4, 15), description="Salary", amount=Decimal("1500.00"), category="Income"), Transaction(id=4, date=dt.date(2025, 4, 20), description="Gas Station #1", amount=Decimal("-35.50"), category="Gas"), ]
    qa_summary = None # Pass None for summary data in direct test
    question1 = "How much did I spend on Gas in April 2025?"; answer1 = answer_financial_question(question1, qa_test_transactions, qa_summary, "2025-04-01", "2025-04-30"); print(f"\nQ: {question1}\nA: {answer1}")
    question2 = "What was my total income in April 2025?"; answer2 = answer_financial_question(question2, qa_test_transactions, qa_summary, "2025-04-01", "2025-04-30"); print(f"\nQ: {question2}\nA: {answer2}")
    question3 = "What was the transaction on 2025-04-10?"; answer3 = answer_financial_question(question3, qa_test_transactions, qa_summary, "2025-04-01", "2025-04-30"); print(f"\nQ: {question3}\nA: {answer3}")
    question4 = "What was my income in March 2025?"; answer4 = answer_financial_question(question4, qa_test_transactions, qa_summary, "2025-04-01", "2025-04-30"); print(f"\nQ: {question4}\nA: {answer4}")


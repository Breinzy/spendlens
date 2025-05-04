import google.generativeai as genai
import os
import logging
from decimal import Decimal
import datetime as dt # Already imported, good.
from collections import Counter
from typing import Dict, Any, List, Optional, Tuple # Added Tuple
from dotenv import load_dotenv
import random # For potential sampling
import json # For parsing LLM response

# Load .env file
load_dotenv()

# Configure logging
# Use a distinct logger name to avoid conflicts if other modules use the root logger
log = logging.getLogger('llm_service')
log.setLevel(logging.INFO)
# Avoid adding multiple handlers if the script is reloaded in some environments
if not log.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)

# --- Global variable for the model ---
model = None
is_configured = False

# --- Attempt initial configuration ---
try:
    GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
    if not GOOGLE_API_KEY:
        log.warning("GOOGLE_API_KEY not found in environment variables during initial load.")
    else:
        log.info(f"Initial load: Found GOOGLE_API_KEY starting with: {GOOGLE_API_KEY[:4]}...")
        genai.configure(api_key=GOOGLE_API_KEY)
        # --- Using gemini-1.5-flash ---
        model = genai.GenerativeModel('gemini-1.5-flash')
        # --- END OF CHANGE ---
        is_configured = True
        log.info(f"Gemini API configured successfully during initial load with model 'gemini-1.5-flash'.")
except ImportError:
    log.error("google.generativeai library not found. Please install it: pip install google-generativeai")
except Exception as e:
    log.error(f"Initial Gemini configuration failed: {e}", exc_info=True) # model remains None

# Import Transaction class definition from parser
# We define it here as well for robustness in case of import issues during direct script execution
class Transaction:
    # Define attributes expected by formatting functions to avoid AttributeError
    id: int = 0 # Add default ID
    date: Optional[dt.date] = None
    description: Optional[str] = None
    amount: Optional[Decimal] = None
    category: Optional[str] = None
    transaction_type: Optional[str] = None
    source_account_type: Optional[str] = None
    source_filename: Optional[str] = None
    raw_description: Optional[str] = None

    # Add __init__ matching the one in parser.py for consistency when creating instances
    def __init__(self, id: int = 0, date: Optional[dt.date] = None, description: Optional[str] = None,
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
        self.raw_description = raw_description if raw_description else description # Fallback


# --- Formatting Function for Transaction List (Q&A) ---
def format_transactions_for_qa(
    transactions: List[Transaction],
    start_date_str: Optional[str] = None,
    end_date_str: Optional[str] = None
    ) -> str:
    """Formats a list of transactions into a concise string for LLM Q&A prompts."""
    if not transactions:
        return "No transaction data provided for the specified period."

    # Transactions are already filtered by date in app.py before calling this
    limit_note = f"\n(Displaying all {len(transactions)} transactions provided for the period)"

    if start_date_str and end_date_str:
        header = f"Transaction List (Period: {start_date_str} to {end_date_str}):"
    elif start_date_str:
        header = f"Transaction List (Period: From {start_date_str} onwards):"
    elif end_date_str:
        header = f"Transaction List (Period: Up to {end_date_str}):"
    else:
        # Reflects that filtering happened upstream if dates are missing
        header = "Transaction List (Full period provided):"

    formatted_list = [header]
    for tx in transactions:
        # Use getattr for safety in case Transaction class definition is missing/different
        date_str = tx.date.isoformat() if hasattr(tx, 'date') and isinstance(tx.date, dt.date) else 'N/A'
        desc = getattr(tx, 'description', 'N/A')
        amount = getattr(tx, 'amount', Decimal('0'))
        # Ensure amount is Decimal before formatting
        amount_str = f"{Decimal(amount):.2f}" if amount is not None else 'N/A'
        category = getattr(tx, 'category', 'N/A')
        formatted_list.append(f"- {date_str}: {desc} ({category}) | Amount: {amount_str}")

    formatted_list.append(limit_note)
    return "\n".join(formatted_list)

# --- Formatting Function for Summary Statistics (Q&A) ---
def format_summary_for_qa(summary_data: Optional[Dict[str, Any]], start_date_str: Optional[str], end_date_str: Optional[str]) -> str:
    """Formats summary statistics into a string for LLM Q&A prompts."""
    if not summary_data:
        return "No summary statistics calculated for the period."

    period_str = "Overall"
    if start_date_str and end_date_str:
        period_str = f"Period: {start_date_str} to {end_date_str}"
    elif start_date_str:
        period_str = f"Period: From {start_date_str}"
    elif end_date_str:
        period_str = f"Period: Up to {end_date_str}"
    else:
        period_str = "Full Period Provided" # Clarify period if dates aren't specified

    formatted_string = f"Summary Statistics ({period_str}):\n"
    # Use Decimal for consistent formatting
    formatted_string += f"- Total Operational Income: ${Decimal(summary_data.get('operational_income', 0)):.2f}\n"
    formatted_string += f"- Total Operational Spending: ${Decimal(summary_data.get('operational_spending', 0)):.2f}\n"
    formatted_string += f"- Net Operational Flow: ${Decimal(summary_data.get('net_operational_flow', 0)):.2f}\n"

    net_spending = summary_data.get('net_spending_by_category', {})
    if net_spending:
         formatted_string += "- Top Net Spending Categories:\n"
         # Sort items by Decimal value, descending
         top_spending = sorted(net_spending.items(), key=lambda item: Decimal(item[1]), reverse=True)[:3] # Top 3
         for cat, amount in top_spending:
             formatted_string += f"  - {cat}: ${Decimal(amount):.2f}\n"
    formatted_string += f"- Total Transactions Analyzed: {summary_data.get('transaction_count', 0)}\n"
    return formatted_string

# --- Formatting Function for Summary/Trends (Summary Generation) ---
def format_data_for_llm(summary_data, trends_data, start_date_str, end_date_str):
    """
    Formats the financial summary and trends data into a string prompt for the LLM summary generation.

    Args:
        summary_data (dict): Dictionary containing financial summary (income, spending, categories).
        trends_data (dict): Dictionary containing month-over-month spending trends.
        start_date_str (str): Start date for the analysis period (YYYY-MM-DD).
        end_date_str (str): End date for the analysis period (YYYY-MM-DD).

    Returns:
        str: A formatted string ready to be used as an LLM prompt.
    """
    prompt_lines = [
        f"Financial Analysis Report ({start_date_str} to {end_date_str})\n",
        "--- Overall Summary ---"
    ]
    # Add overall summary details using Decimal for consistency
    prompt_lines.append(f"Total Income: ${Decimal(summary_data.get('total_income', 0)):,.2f}")
    prompt_lines.append(f"Total Operational Spending: ${Decimal(summary_data.get('total_operational_spending', 0)):,.2f}")
    prompt_lines.append(f"Net Operational Cash Flow: ${Decimal(summary_data.get('net_operational_flow', 0)):,.2f}")
    prompt_lines.append(f"Total Transfers & Payments: ${Decimal(summary_data.get('total_transfers_and_payments', 0)):,.2f}")
    prompt_lines.append(f"Net Change (including transfers): ${Decimal(summary_data.get('net_change_all', 0)):,.2f}\n")

    # Add spending by category
    prompt_lines.append("--- Spending by Category ---")
    spending_categories = summary_data.get('spending_by_category', {})
    if spending_categories:
        # Sort categories by amount spent (absolute value), descending
        sorted_categories = sorted(spending_categories.items(), key=lambda item: abs(Decimal(item[1])), reverse=True)
        for category, amount in sorted_categories:
            # Display spending as positive number
            prompt_lines.append(f"- {category}: ${abs(Decimal(amount)):,.2f}")
    else:
        prompt_lines.append("No spending data available for this period.")
    prompt_lines.append("") # Add spacing

    # Add monthly trends if available
    prompt_lines.append("--- Monthly Spending Trends ---")
    # Check if trends_data and the 'comparison' key exist and are not empty
    if trends_data and trends_data.get('comparison'):
        current_month = trends_data.get('current_month_str', 'Current Month')
        previous_month = trends_data.get('previous_month_str', 'Previous Month')
        prompt_lines.append(f"Comparison between {previous_month} and {current_month}:\n")
        comparison = trends_data['comparison']
        # Sort categories alphabetically for consistent trend reporting
        sorted_trend_categories = sorted(comparison.keys())
        for category in sorted_trend_categories:
            trend = comparison[category]
            # Ensure values are Decimal for calculations and formatting
            current_amount_dec = Decimal(trend.get('current_amount', 0))
            change_dec = Decimal(trend.get('change', 0))
            percent_change_val = trend.get('percent_change') # Can be None

            change_str = f"${change_dec:,.2f}"
            percent_change_str = f"{float(percent_change_val):.1f}%" if percent_change_val is not None else "N/A"
            direction = "increase" if change_dec > 0 else "decrease" if change_dec < 0 else "no change"

            if direction != "no change":
                 # Show spending as positive, indicate direction clearly
                prompt_lines.append(f"- {category}: Spent ${abs(current_amount_dec):,.2f} ({direction} of {change_str} / {percent_change_str} from {previous_month})")
            else:
                 prompt_lines.append(f"- {category}: Spent ${abs(current_amount_dec):,.2f} (no change from {previous_month})")

        # Ensure total trend values are Decimal
        total_current_spending_dec = Decimal(trends_data.get('total_current_spending', 0))
        total_change_dec = Decimal(trends_data.get('total_change', 0))
        total_percent_change_val = trends_data.get('total_percent_change') # Can be None
        total_percent_change_str = f"{float(total_percent_change_val):.1f}%" if total_percent_change_val is not None else "N/A"

        prompt_lines.append(f"\nTotal Spending Trend: {current_month} spending was ${abs(total_current_spending_dec):,.2f}, a change of ${total_change_dec:,.2f} ({total_percent_change_str}) from {previous_month}.")

    else:
        prompt_lines.append("Not enough data for monthly trend comparison (requires at least two full months).")

    return "\n".join(prompt_lines)


# --- Main LLM Summary Generation Function ---
def generate_financial_summary(summary_data: Dict[str, Any], trends_data: Dict[str, Any], start_date_str: str, end_date_str: str) -> str:
    """Generates a natural language financial summary using the configured Gemini model."""
    global model, is_configured
    # Re-check configuration if needed
    if not is_configured:
        log.warning("Model not configured initially, attempting configuration in generate_financial_summary...")
        try:
            API_KEY = os.environ.get('GOOGLE_API_KEY')
            if not API_KEY:
                log.error("GOOGLE_API_KEY still not found in environment.")
                return "Error: LLM model could not be configured - API key missing."
            else:
                log.info(f"Found GOOGLE_API_KEY starting with: {API_KEY[:4]}... in function.")
                genai.configure(api_key=API_KEY)
                # --- Using gemini-1.5-flash ---
                model = genai.GenerativeModel('gemini-1.5-flash')
                # --- END OF CHANGE ---
                is_configured = True
                log.info(f"Gemini API configured successfully within function with model 'gemini-1.5-flash'.")
        except Exception as e:
            log.error(f"Gemini configuration failed within function: {e}", exc_info=True)
            return f"Error: LLM model configuration failed ({type(e).__name__})."

    # Final check if model object exists
    if model is None:
        log.error("generate_financial_summary called but model object is None after configuration attempt.")
        return "Error: LLM model is not available."

    formatted_data = format_data_for_llm(summary_data, trends_data, start_date_str, end_date_str)

    # Updated prompt for conciseness and clarity
    prompt = f"""
You are SpendLens, a friendly financial assistant. Your goal is to provide clear, simple insights based *only* on the data provided below.
Analyze the following financial data for the period {start_date_str} to {end_date_str}.
Provide a brief summary (2-3 key bullet points) using simple words.
Highlight the main points like net cash flow (income vs spending), the biggest spending areas, and any significant spending changes compared to the previous month (if trend data is available).
Keep the tone helpful and encouraging. Avoid financial jargon.

Financial Data:
{formatted_data}

Brief Summary:
"""
    log.info(f"Generating financial summary with Gemini for period {start_date_str} to {end_date_str}...")
    try:
        # Ensure model is not None before calling generate_content
        if model:
            log.debug("Calling model.generate_content for summary...")
            response = model.generate_content(prompt)
            log.debug(f"Received response object for summary: {type(response)}")

            # Check response structure carefully
            if hasattr(response, 'text') and response.text:
                generated_text = response.text.strip()
                refusal_phrases = ["cannot provide", "not available in the provided data", "don't have access", "unable to"]
                if any(phrase in generated_text.lower() for phrase in refusal_phrases):
                     log.warning(f"LLM Summary generation resulted in a refusal/cannot answer: {generated_text}")
                else:
                     log.info("Successfully generated summary.")
                return generated_text
            elif response.prompt_feedback and response.prompt_feedback.block_reason:
                 block_reason = response.prompt_feedback.block_reason
                 log.error(f"Gemini response blocked. Reason: {block_reason}")
                 return f"Error: Could not generate summary because the request was blocked ({block_reason})."
            else:
                log.error(f"Gemini response missing text or blocked without reason. Full response: {response}")
                return "Error: Could not generate summary due to unexpected API response format."
        else:
            log.error("Model is None just before calling generate_content.")
            return "Error: LLM Model is unexpectedly unavailable."

    except Exception as e:
        log.error(f"Error calling Gemini API for summary: {e}", exc_info=True)
        return f"Error: Could not generate summary due to an API error ({type(e).__name__})."


# --- LLM Q&A Function ---
# --- MODIFIED RETURN TYPE ---
def answer_financial_question(
    question: str,
    transactions: List[Transaction],
    summary_data: Optional[Dict[str, Any]],
    start_date_str: Optional[str] = None,
    end_date_str: Optional[str] = None,
    pre_calculated_result: Optional[Decimal] = None # New argument
    ) -> Tuple[str, str]: # Return (answer_text, status)
    # Status can be: 'success', 'blocked', 'error', 'cannot_answer'
    # --- END OF MODIFIED RETURN TYPE ---
    """Uses the Gemini API to answer a specific financial question based on provided data."""
    global model, is_configured
    # Ensure model is configured (similar logic as generate_financial_summary)
    if not is_configured:
        log.warning("Model not configured initially, attempting configuration for Q&A...")
        try:
            API_KEY = os.environ.get('GOOGLE_API_KEY')
            if not API_KEY: log.error("GOOGLE_API_KEY still not found."); return "Error: LLM model could not be configured - API key missing.", "error"
            else:
                log.info(f"Found GOOGLE_API_KEY starting with: {API_KEY[:4]}... in Q&A function.")
                genai.configure(api_key=API_KEY)
                # --- Using gemini-1.5-flash ---
                model = genai.GenerativeModel('gemini-1.5-flash')
                # --- END OF CHANGE ---
                is_configured = True
                log.info(f"Gemini API configured successfully within Q&A function with model 'gemini-1.5-flash'.")
        except Exception as e: log.error(f"Gemini configuration failed within Q&A function: {e}", exc_info=True); return f"Error: LLM model configuration failed ({type(e).__name__}).", "error"

    if model is None:
        log.error("answer_financial_question called but model object is None.")
        return "Error: LLM model is not available.", "error"

    # --- Get Current Date ---
    current_date = dt.date.today()
    current_date_str = current_date.isoformat()
    log.info(f"Current date for context: {current_date_str}")

    # --- Determine if details are requested ---
    details_requested = any(detail_word in question.lower() for detail_word in ["show transaction", "list transaction", "associated math", "details", "breakdown"])

    # --- Conditionally format transaction list ---
    formatted_transactions = "" # Initialize as empty
    include_tx_list = pre_calculated_result is None or details_requested

    if include_tx_list:
        formatted_transactions = format_transactions_for_qa(transactions, start_date_str, end_date_str)
        log.debug("Including transaction list in Q&A prompt.")
    else:
        formatted_transactions = "(Transaction list omitted as pre-calculated result is provided and details were not explicitly requested)"
        log.debug("Omitting transaction list from Q&A prompt.")
    # --- End conditional formatting ---

    # Format the summary data
    formatted_summary = format_summary_for_qa(summary_data, start_date_str, end_date_str)

    # Determine the data scope description for the prompt
    data_scope_info = "the available data (defaulting to last ~2 years if no dates specified)"
    if start_date_str and end_date_str: data_scope_info = f"data between {start_date_str} and {end_date_str}"
    elif start_date_str: data_scope_info = f"data since {start_date_str}"
    elif end_date_str: data_scope_info = f"data up to {end_date_str}"

    # --- Construct the Prompt incorporating pre-calculated result ---
    pre_calc_info = ""
    formatted_pre_calc = "" # Initialize for potential use in prompt
    pre_calc_is_spending = False # Flag to help with phrasing
    if pre_calculated_result is not None:
        # Format the pre-calculated result for the prompt
        formatted_pre_calc = f"${abs(pre_calculated_result):,.2f}" # Use absolute value for display
        pre_calc_is_spending = pre_calculated_result < 0 # Check if it was spending
        pre_calc_info = f"A pre-calculated result for the user's query is available: {formatted_pre_calc}."
        log.info(f"Providing pre-calculated result to LLM: {formatted_pre_calc} (Original: {pre_calculated_result})")
    else:
        pre_calc_info = "No pre-calculated result was provided for this query. You must analyze the data below if necessary."
        log.info("No pre-calculated result provided to LLM.")

    # --- UPDATED PROMPT LOGIC ---
    prompt_lines = [
        "You are SpendLens, a helpful financial assistant.",
        f"The current date is: {current_date_str}. Use this date ONLY to understand relative time references in the user's question (like 'this year', 'last month').",
        f"Answer the following user question based *only* on the provided financial data ({data_scope_info}) and the pre-calculated result (if provided). Do NOT use any external knowledge for financial calculations or information beyond the current date.",
        f"\nPre-calculated Result Information:\n{pre_calc_info}"
    ]

    # --- Simplified Prompt Instructions when Pre-calculated (and no details requested) ---
    if pre_calculated_result is not None and not details_requested:
        log.debug("Using simplified prompt for pre-calculated result.")
        prompt_lines.append("\nInstructions:")
        prompt_lines.append(f"- The user asked: \"{question}\"")
        prompt_lines.append(f"- The pre-calculated answer based on their data is {formatted_pre_calc}.")
        # Add phrasing guidance based on whether it was income or spending
        if pre_calc_is_spending:
             prompt_lines.append(f"- State this concisely, for example: 'You spent {formatted_pre_calc} on [Category/Period].'")
        else: # Assume income or other positive value
             prompt_lines.append(f"- State this concisely, for example: 'Total income for [Period] was {formatted_pre_calc}.'")
        prompt_lines.append("- Do not add any extra analysis, commentary, or mention the calculation.")

    # --- Detailed Prompt Instructions (when no pre-calc or details requested) ---
    else:
        log.debug("Using detailed prompt for Q&A.")
        prompt_lines.extend([
            "\nAvailable Data:",
            f"1. Summary Statistics: Provides overall figures for the period. **DO NOT use for questions about specific months/dates.**\n{formatted_summary}",
            f"\n2. Transaction List: Contains individual transactions. **This list is only included below if NO pre-calculated result was provided OR if the user asked for details.**\n{formatted_transactions}",
            "\nInstructions:",
            f"- **PRIORITY:** If a pre-calculated result is provided ({formatted_pre_calc if pre_calculated_result is not None else 'N/A'}) AND the user DID NOT ask for details/breakdown, state that result directly and concisely.",
            "    - If the pre-calculated result represents spending (negative original value), phrase it like 'You spent [positive amount] on [Category/Period]'.",
            "    - If the pre-calculated result represents income (positive original value), phrase it like 'Total income for [Period] was [amount]'.",
            "- **If a pre-calculated result IS provided AND the user DID ask for details/breakdown:** State the pre-calculated result first (phrased appropriately for spending/income), then list the relevant transactions from the Transaction List (if included above) that match the criteria used for the pre-calculation. If the transaction list was omitted, state the pre-calculated result and mention that details are not available in this view.",
            "- **If NO pre-calculated result is provided:**",
            "    - Base your answer strictly on the financial data provided above, primarily the Transaction List.",
            "    - Use the current date ({current_date_str}) to interpret relative time references in the question.",
            "    - **If the question asks for totals/amounts for specific dates, months, or categories:**",
            "        - Calculate the requested total by summing the 'Amount' from relevant entries in the **Transaction List** ONLY.",
            "        - Ensure you filter by the correct date range (derived from the question and current date) and category (if specified).",
            "        - **INCOME CALCULATION:** When calculating 'income', sum only transactions where the category is EXACTLY 'Income'. **EXPLICITLY EXCLUDE transactions categorized as 'Payments', even if their amount is positive.**",
            "        - **State ONLY the final calculated total.** Phrase spending as 'You spent [positive amount]' and income as 'Total income was [amount]'.",
            "        - If no matching transactions are found in the list (respecting the category filter), state that clearly.",
            "    - **DO NOT show calculation steps or list individual transactions unless specifically asked.**",
            "- If the answer cannot be determined from the provided data, state that the information is not available in the provided data.",
            "- Be concise."
        ])
    # --- End Prompt Logic ---

    prompt_lines.append(f"\nUser Question: {question}")
    prompt_lines.append("\nAnswer:")
    prompt = "\n".join(prompt_lines)
    # log.debug(f"Final Q&A Prompt:\n{prompt}") # Uncomment to log full prompt if needed


    log.info(f"Answering question with Gemini: '{question}' (Data scope: {data_scope_info}, Current Date Context: {current_date_str}, Pre-calc provided: {pre_calculated_result is not None}, Including Tx List: {include_tx_list})")
    try:
        if model:
            log.debug("Calling model.generate_content for Q&A...")
            response = model.generate_content(prompt) # Using the updated prompt
            log.debug(f"Received response object for Q&A: {type(response)}")

            # --- UPDATED RESPONSE HANDLING ---
            if hasattr(response, 'text') and response.text:
                generated_text = response.text.strip()
                log.info("Successfully generated answer.")
                # Check for common refusal phrases
                refusal_phrases = ["cannot provide", "not available in the provided data", "don't have access", "unable to", "cannot be determined"]
                if any(phrase in generated_text.lower() for phrase in refusal_phrases):
                     log.warning(f"LLM Q&A resulted in a refusal/cannot answer: {generated_text}")
                     return generated_text, "cannot_answer"
                else:
                    # Removed fallback check - rely on prompt instructions
                    return generated_text, "success"
            elif response.prompt_feedback and response.prompt_feedback.block_reason:
                 block_reason = response.prompt_feedback.block_reason
                 error_message = f"Error: Could not get answer because the request was blocked by the safety filter ({block_reason}). Please rephrase your question."
                 log.error(f"Gemini Q&A response blocked. Reason: {block_reason}")
                 return error_message, "blocked" # Return specific status
            elif not response.candidates:
                 log.error(f"Gemini Q&A response missing candidates. Response: {response}")
                 block_reason_str = "Unknown"
                 if response.prompt_feedback and response.prompt_feedback.block_reason:
                     block_reason_str = response.prompt_feedback.block_reason
                 error_message = f"Error: Could not get answer. The response was empty or blocked (Reason: {block_reason_str})."
                 return error_message, "blocked" # Treat as blocked
            else:
                 error_message = "Error: Could not get answer due to unexpected API response format."
                 log.error(f"Gemini Q&A response missing text or blocked without clear reason. Response: {response}")
                 return error_message, "error"
            # --- END UPDATED RESPONSE HANDLING ---
        else:
            log.error("Model is None just before calling generate_content for Q&A.")
            return "Error: LLM Model is unexpectedly unavailable.", "error"

    except Exception as e:
        error_message = f"Error: Could not get answer due to an API error ({type(e).__name__})."
        log.error(f"Error calling Gemini API for Q&A: {e}", exc_info=True)
        return error_message, "error"

# --- MODIFIED FUNCTION: LLM Batch Category Suggestion ---
def suggest_categories_for_transactions(
    transactions_to_categorize: List[Transaction],
    valid_categories: List[str],
    existing_rules: Optional[Dict[str, str]] = None, # Pass existing rules for context
    # Removed sample_size, process all provided
    ) -> Dict[str, str]:
    """
    Uses the LLM to suggest categories for a batch of uncategorized transactions.

    Args:
        transactions_to_categorize: A list of Transaction objects that are currently 'Uncategorized'.
        valid_categories: A list of allowed category names for the LLM to choose from.
        existing_rules: Optional dictionary of existing rules (user/vendor) to provide context.

    Returns:
        A dictionary mapping original transaction descriptions (lowercase) to suggested category names.
    """
    global model, is_configured
    if not is_configured or model is None:
        log.error("LLM not configured. Cannot suggest categories.")
        return {}

    if not transactions_to_categorize:
        log.info("No transactions provided for LLM categorization.")
        return {}

    if not valid_categories:
        log.error("No valid categories provided for LLM suggestion.")
        return {}

    log.info(f"Attempting to suggest categories for {len(transactions_to_categorize)} transactions using LLM batch.")

    # --- Prepare Batch Prompt ---
    indexed_descriptions = {}
    prompt_lines = ["Please suggest the single most likely category for each transaction description listed below."]
    prompt_lines.append(f"Choose the best category ONLY from the following list: {', '.join(valid_categories)}")
    prompt_lines.append("\nTransaction Descriptions to Categorize:")

    unique_descriptions_to_process = {} # Use dict to handle duplicate descriptions efficiently
    for i, tx in enumerate(transactions_to_categorize):
        # Ensure description and amount exist and are valid before processing
        if hasattr(tx, 'description') and tx.description and hasattr(tx, 'amount') and tx.amount is not None:
            try:
                # Ensure amount is Decimal for formatting
                amount_dec = Decimal(tx.amount)
                desc_lower = tx.description.lower().strip()
                if desc_lower not in unique_descriptions_to_process:
                     unique_descriptions_to_process[desc_lower] = f"{i+1}. Description: \"{tx.description}\", Amount: {amount_dec:.2f}"
            except (InvalidOperation, TypeError):
                 log.warning(f"Skipping transaction ID {getattr(tx, 'id', 'N/A')} in batch prep due to invalid amount: {tx.amount}")
                 continue
        else:
            log.debug(f"Skipping transaction ID {getattr(tx, 'id', 'N/A')} in batch prep due to missing description or amount.")


    if not unique_descriptions_to_process:
         log.warning("No valid descriptions found in the transactions to categorize.")
         return {}

    # Add unique descriptions to prompt
    for key, formatted_line in unique_descriptions_to_process.items():
         prompt_lines.append(formatted_line)


    # Add context examples (optional, keep concise)
    if existing_rules:
        example_count = 0
        prompt_lines.append("\nExample categorizations based on keywords:")
        if existing_rules:
            sample_keys = random.sample(list(existing_rules.keys()), min(len(existing_rules), 5))
            for key in sample_keys:
                cat = existing_rules[key]
                prompt_lines.append(f"- If description contains '{key}', category is '{cat}'.")
                example_count += 1

    prompt_lines.append("\nProvide your suggestions ONLY as a valid JSON object where keys are the original lowercase descriptions (exactly as listed above without the index number) and values are the suggested categories from the provided list.")
    prompt_lines.append("Example JSON output format: {\"description 1 lowercase\": \"Suggested Category 1\", \"description 2 lowercase\": \"Suggested Category 2\", ...}")
    prompt_lines.append("JSON Response:")

    full_prompt = "\n".join(prompt_lines)
    # log.debug(f"Batch Category Suggestion Prompt:\n{full_prompt}") # Log prompt if needed

    # --- Single API Call ---
    suggested_rules: Dict[str, str] = {}
    try:
        log.debug("Calling model.generate_content for batch category suggestion...")
        response = model.generate_content(full_prompt)
        log.debug(f"Received response object for batch category suggestion: {type(response)}")

        if hasattr(response, 'text') and response.text:
            llm_response_text = response.text.strip()
            log.debug(f"LLM Raw Response Text for JSON parsing:\n{llm_response_text}") # Log the raw text

            # --- Improved JSON Extraction ---
            json_string = None
            try:
                start_index = llm_response_text.find('{')
                end_index = llm_response_text.rfind('}')
                if start_index != -1 and end_index != -1 and end_index > start_index:
                    json_string = llm_response_text[start_index : end_index + 1]
                    log.debug(f"Extracted potential JSON string:\n{json_string}")
                else:
                    log.error("Could not find valid JSON object delimiters '{' and '}' in LLM response.")
            except Exception as find_err: log.error(f"Error finding JSON delimiters: {find_err}")

            if json_string:
                try:
                    suggestions = json.loads(json_string)
                    if isinstance(suggestions, dict):
                        valid_suggestions_count = 0
                        for desc_key_from_llm, suggested_cat_raw in suggestions.items():
                            if not isinstance(desc_key_from_llm, str) or not isinstance(suggested_cat_raw, str):
                                log.warning(f"Skipping invalid suggestion format: key={desc_key_from_llm}, value={suggested_cat_raw}")
                                continue
                            suggested_cat_normalized = None
                            for valid_cat in valid_categories:
                                 if valid_cat.lower() == suggested_cat_raw.strip().lower():
                                     suggested_cat_normalized = valid_cat; break
                            if suggested_cat_normalized and suggested_cat_normalized != 'Uncategorized':
                                 llm_key_normalized = desc_key_from_llm.lower().strip()
                                 if llm_key_normalized in unique_descriptions_to_process:
                                     suggested_rules[llm_key_normalized] = suggested_cat_normalized
                                     valid_suggestions_count += 1
                                     log.info(f"Matched LLM key '{llm_key_normalized}' to original description.")
                                 else:
                                     found_match = False
                                     for original_key in unique_descriptions_to_process.keys():
                                         if original_key in llm_key_normalized:
                                             suggested_rules[original_key] = suggested_cat_normalized
                                             valid_suggestions_count += 1
                                             log.warning(f"Loosely matched LLM key '{llm_key_normalized}' to original '{original_key}'.")
                                             found_match = True; break
                                     if not found_match: log.warning(f"LLM returned unknown key: '{desc_key_from_llm}'. Skipping.")
                            else: log.info(f"LLM suggested invalid/Uncategorized '{suggested_cat_raw}' for '{desc_key_from_llm}'. Skipping.")
                        log.info(f"Successfully parsed/validated {valid_suggestions_count} suggestions.")
                    else: log.error(f"Extracted string not parsed as dict: {json_string}")
                except json.JSONDecodeError as json_err: log.error(f"Failed JSON parse: {json_err}. String: {json_string}")
                except Exception as parse_err: log.error(f"Error processing suggestions: {parse_err}", exc_info=True)
            else: log.error("Could not extract JSON string from LLM response.")

        elif response.prompt_feedback and response.prompt_feedback.block_reason: log.warning(f"LLM batch suggestion blocked. Reason: {response.prompt_feedback.block_reason}")
        else: log.warning(f"LLM batch suggestion failed. Unexpected response: {response}")
    except Exception as e: log.error(f"Error calling Gemini API for batch suggestion: {e}", exc_info=True)

    log.info(f"LLM batch category suggestion finished. Returning {len(suggested_rules)} valid suggestions.")
    return suggested_rules
# --- END OF MODIFIED FUNCTION ---


# --- Testing Block ---
if __name__ == '__main__':
    log.info("llm_service.py executed directly for testing.")

    # Ensure API Key is available for testing
    if not is_configured:
        log.warning("LLM not configured. Testing will be limited.")

    # Example Mock Data (using Decimal for amounts)
    mock_summary = { 'total_income': Decimal('5000.00'), 'total_operational_spending': Decimal('-3500.00'), 'net_operational_flow': Decimal('1500.00'), 'total_transfers_and_payments': Decimal('-1000.00'), 'net_change_all': Decimal('500.00'), 'spending_by_category': { 'Food': Decimal('-1200.00'), 'Shopping': Decimal('-800.00'), 'Utilities': Decimal('-500.00'), 'Rent': Decimal('-1000.00') }, 'operational_income': Decimal('5000.00'), 'operational_spending': Decimal('-3500.00'), 'net_spending_by_category': { 'Food': Decimal('1200.00'), 'Shopping': Decimal('800.00'), 'Utilities': Decimal('500.00'), 'Rent': Decimal('1000.00') }, 'transaction_count': 100 }
    mock_trends = { 'current_month_str': 'April 2025', 'previous_month_str': 'March 2025', 'total_current_spending': Decimal('-3500.00'), 'total_previous_spending': Decimal('-3200.00'), 'total_change': Decimal('-300.00'), 'total_percent_change': Decimal('-9.4'), 'comparison': { 'Food': {'current_amount': Decimal('-1200.00'), 'previous_amount': Decimal('-1100.00'), 'change': Decimal('-100.00'), 'percent_change': Decimal('-9.1')}, 'Shopping': {'current_amount': Decimal('-800.00'), 'previous_amount': Decimal('-900.00'), 'change': Decimal('100.00'), 'percent_change': Decimal('11.1')}, 'Utilities': {'current_amount': Decimal('-500.00'), 'previous_amount': Decimal('-500.00'), 'change': Decimal('0.00'), 'percent_change': Decimal('0.0')}, 'Rent': {'current_amount': Decimal('-1000.00'), 'previous_amount': Decimal('-700.00'), 'change': Decimal('-300.00'), 'percent_change': Decimal('-42.9')} } }
    mock_start = "2025-04-01"; mock_end = "2025-04-30"

    print("\n--- Testing format_data_for_llm ---")
    formatted_llm_data = format_data_for_llm(mock_summary, mock_trends, mock_start, mock_end); print(formatted_llm_data)

    if is_configured and model:
        print("\n--- Testing LLM Summary Generation ---")
        summary_text = generate_financial_summary(mock_summary, mock_trends, mock_start, mock_end); print("\nGenerated Summary:"); print(summary_text)
    else: print("\n--- Skipping LLM Summary Generation (Not Configured) ---")

    print("\n--- Testing LLM Q&A ---")
    qa_test_transactions = [ Transaction(id=1, date=dt.date(2025, 4, 5), description="Grocery Mart", amount=Decimal("-55.00"), category="Groceries"), Transaction(id=2, date=dt.date(2025, 4, 10), description="Gas Station #1", amount=Decimal("-40.00"), category="Gas"), Transaction(id=3, date=dt.date(2025, 4, 15), description="Salary April", amount=Decimal("1500.00"), category="Income"), Transaction(id=4, date=dt.date(2025, 4, 20), description="Gas Station #1", amount=Decimal("-35.50"), category="Gas"), Transaction(id=5, date=dt.date(2025, 3, 15), description="Salary March", amount=Decimal("1450.00"), category="Income"), Transaction(id=6, date=dt.date(2025, 3, 10), description="Restaurant", amount=Decimal("-60.00"), category="Food"), Transaction(id=7, date=dt.date(2025, 3, 5), description="Payment Thank You-Mobile", amount=Decimal("819.17"), category="Payments"), ]
    qa_summary_for_test = { 'operational_income': Decimal('2950.00'), 'operational_spending': Decimal('-190.50'), 'net_operational_flow': Decimal('2759.50'), 'net_spending_by_category': {'Groceries': Decimal('55.00'), 'Gas': Decimal('75.50'), 'Food': Decimal('60.00')}, 'transaction_count': 7 }

    if is_configured and model:
        print("\n--- Test 1: Income March (Pre-calculated) ---")
        q1 = "what is my income for march 2025"; pre_calc1 = Decimal("1450.00"); ans1, stat1 = answer_financial_question(q1, qa_test_transactions, qa_summary_for_test, "2025-03-01", "2025-04-30", pre_calculated_result=pre_calc1); print(f"Q: {q1}\nA: {ans1} (Status: {stat1})")

        print("\n--- Test 1b: Income March (Pre-calculated + Details) ---")
        q1b = "what is my income for march 2025 and show transactions"; ans1b, stat1b = answer_financial_question(q1b, qa_test_transactions, qa_summary_for_test, "2025-03-01", "2025-04-30", pre_calculated_result=pre_calc1); print(f"Q: {q1b}\nA: {ans1b} (Status: {stat1b})")

        print("\n--- Test 2: Specific Transaction (No Pre-calculation) ---")
        q2 = "What was the transaction on 2025-04-10?"; ans2, stat2 = answer_financial_question(q2, qa_test_transactions, qa_summary_for_test, "2025-03-01", "2025-04-30", pre_calculated_result=None); print(f"Q: {q2}\nA: {ans2} (Status: {stat2})")

        print("\n--- Test 3: Spending April (Pre-calculated) ---")
        q3 = "how much did i spend in april 2025"; pre_calc3 = Decimal("-130.50"); ans3, stat3 = answer_financial_question(q3, qa_test_transactions, qa_summary_for_test, "2025-03-01", "2025-04-30", pre_calculated_result=pre_calc3); print(f"Q: {q3}\nA: {ans3} (Status: {stat3})")

        # --- Test 3b: Spending Food April (Pre-calculated) ---
        print("\n--- Test 3b: Spending Food April (Pre-calculated) ---")
        q3b = "how much did i spend on food in april 2025?"; pre_calc3b = Decimal("-0.00"); # Example if no food spending in April
        ans3b, stat3b = answer_financial_question(q3b, qa_test_transactions, qa_summary_for_test, "2025-03-01", "2025-04-30", pre_calculated_result=pre_calc3b); print(f"Q: {q3b}\nA: {ans3b} (Status: {stat3b})")


        print("\n--- Test 4: LLM Batch Category Suggestion ---")
        uncategorized_tx = [ Transaction(id=100, date=dt.date(2025, 4, 1), description="SQC*SQ *MERCHANT CAFE", amount=Decimal("-12.50"), category="Uncategorized"), Transaction(id=101, date=dt.date(2025, 4, 2), description="TST* LOCAL COFFEE SHOP", amount=Decimal("-4.75"), category="Uncategorized"), Transaction(id=102, date=dt.date(2025, 4, 3), description="VENMO PAYMENT JANE DOE", amount=Decimal("-50.00"), category="Uncategorized"), Transaction(id=103, date=dt.date(2025, 4, 4), description="PARKING GARAGE FEE", amount=Decimal("-15.00"), category="Uncategorized"), ]
        valid_cats = ["Food", "Coffee Shops", "Transfers", "Shopping", "Travel", "Automotive", "Utilities", "Rent", "Income", "Payments", "Uncategorized"]
        existing_context = {"starbucks": "Coffee Shops", "shell": "Gas", "venmo": "Transfers"}
        suggested_rules_map = suggest_categories_for_transactions(uncategorized_tx, valid_cats, existing_context); print("Suggested Rules Map (description -> category):"); print(suggested_rules_map)

    else: print("\n--- Skipping LLM Q&A / Suggestion Testing (Not Configured) ---")


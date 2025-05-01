import os
import json
import logging
from pathlib import Path
from werkzeug.exceptions import NotFound, BadRequest
import datetime as dt
from dateutil.relativedelta import relativedelta
import re # Import regex for parsing query
from flask import Flask, request, jsonify, abort
from werkzeug.utils import secure_filename
from decimal import Decimal
from dotenv import load_dotenv

# Load .env file right after imports
load_dotenv()

# Imports
from parser import Transaction, parse_checking_csv, parse_credit_csv
from insights import (
    calculate_summary_insights,
    calculate_monthly_trends,
    identify_recurring_transactions,
    analyze_frequent_spending,
    find_potential_duplicate_recurring
)
from database import (
    init_db, add_transactions, get_all_transactions,
    update_transaction_category, save_user_rule,
    get_transaction_by_id, DATABASE_FILE
)
from llm_service import generate_financial_summary, answer_financial_question

# Configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [APP] %(message)s')
app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'; ALLOWED_EXTENSIONS = {'csv'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
Path(UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)

# Helpers
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal): return str(obj)
        if obj == float('inf'): return "Infinity"
        if obj == float('-inf'): return "-Infinity"
        if isinstance(obj, dt.date): return obj.isoformat()
        return super(DecimalEncoder, self).default(obj)
app.json_encoder = DecimalEncoder

# --- Flask Routes ---
# (Previous routes remain unchanged)
@app.route('/')
def index():
    if not DATABASE_FILE.exists(): init_db()
    return "SpendLens Backend is running! Database is ready."

@app.route('/upload', methods=['POST'])
def upload_files():
    # ... (upload logic - unchanged) ...
    newly_parsed_transactions = []
    errors = []
    file_keys = ['checking_file', 'credit_file']
    if not request.files: abort(400, description="No file part in the request.")
    uploaded_files_count = 0
    for key in file_keys:
        if key in request.files:
            file = request.files[key]
            if file.filename == '': continue
            if file and allowed_file(file.filename):
                uploaded_files_count += 1
                filename = secure_filename(file.filename)
                file_path = Path(app.config['UPLOAD_FOLDER']) / filename
                try:
                    file.save(str(file_path)); logging.info(f"File '{filename}' saved.")
                    parsed_txs = []
                    if 'checking' in filename.lower(): parsed_txs = parse_checking_csv(file_path)
                    elif 'credit' in filename.lower(): parsed_txs = parse_credit_csv(file_path)
                    else: errors.append(f"Could not determine parser for file: {filename}")
                    if parsed_txs: newly_parsed_transactions.extend(parsed_txs); logging.info(f"Parsed {len(parsed_txs)} from {filename}.")
                    elif not any(e.startswith(f"Could not determine parser for file: {filename}") for e in errors): errors.append(f"No transactions parsed or error during parsing for {filename}.")
                except Exception as e: errors.append(f"Error processing file {filename}: {str(e)}"); logging.error(f"Error processing file {filename}: {e}", exc_info=True)
                finally:
                    if file_path.exists():
                        try: os.remove(file_path); logging.info(f"Removed temp file: {file_path}")
                        except OSError as remove_err: logging.error(f"Error removing temp file {file_path}: {remove_err}")
            elif file: errors.append(f"File type not allowed for {file.filename}")
    if uploaded_files_count == 0 and not errors: abort(400, description="No valid CSV files were uploaded.")
    total_parsed = len(newly_parsed_transactions)
    logging.info(f"Parsing complete. Saving {total_parsed} transactions (clear_existing=True).")
    db_save_error = None
    try: add_transactions(newly_parsed_transactions, clear_existing=True); logging.info(f"DB save complete.")
    except Exception as db_err: db_save_error = f"DB error: {str(db_err)}"; errors.append(db_save_error); logging.error(f"DB error: {db_err}", exc_info=True); total_parsed = 0
    response_data = {"message": f"Processed {uploaded_files_count} file(s). Saved {total_parsed} new transactions.", "errors": errors}
    status_code = 200 if db_save_error is None else 500
    if status_code == 200 and errors: status_code = 207
    return jsonify(response_data), status_code

@app.route('/transactions', methods=['GET'])
def get_transactions():
    # ... (filtering logic - unchanged) ...
    logging.info("'/transactions' endpoint called.")
    start_date_str = request.args.get('start_date'); end_date_str = request.args.get('end_date'); category_filter = request.args.get('category')
    if start_date_str:
        try: dt.date.fromisoformat(start_date_str)
        except ValueError: abort(400, description="Invalid start_date format.")
    if end_date_str:
        try: dt.date.fromisoformat(end_date_str)
        except ValueError: abort(400, description="Invalid end_date format.")
    logging.info(f"Filtering with: start={start_date_str}, end={end_date_str}, category='{category_filter}'")
    try:
        filtered_transactions = get_all_transactions(start_date=start_date_str, end_date=end_date_str, category=category_filter)
        transactions_dict_list = [tx.to_dict() for tx in filtered_transactions]
        logging.info(f"Returning {len(transactions_dict_list)} filtered transactions.")
        return jsonify(transactions_dict_list)
    except Exception as e: logging.error(f"Error retrieving filtered transactions: {e}", exc_info=True); abort(500)

@app.route('/summary', methods=['GET'])
def get_summary():
    # ... (summary logic - unchanged) ...
    logging.info("'/summary' endpoint called.")
    try:
        all_db_transactions = get_all_transactions()
        logging.info(f"Fetched {len(all_db_transactions)} for summary.")
        if not all_db_transactions: return jsonify({"message": "No transactions found."}), 404
        summary_data = calculate_summary_insights(all_db_transactions)
        logging.info("Summary calculation complete.")
        return jsonify(summary_data)
    except Exception as e: logging.error(f"Error calculating summary: {e}", exc_info=True); abort(500)

@app.route('/transactions/<int:transaction_id>/category', methods=['PUT'])
def update_category_put(transaction_id):
    # ... (PUT update logic - unchanged) ...
    logging.info(f"'/transactions/{transaction_id}/category' (PUT).")
    raw_data = request.data; logging.info(f"DEBUG: Raw data: {raw_data}")
    if not request.is_json: abort(400, description=f"Request must be JSON.")
    data = request.get_json()
    if data is None: abort(400, description="Failed to decode JSON.")
    if 'category' not in data or not isinstance(data['category'], str) or not data['category'].strip(): abort(400, description="Invalid 'category' field.")
    new_category = data['category'].strip()
    logging.info(f"Attempting PUT update ID {transaction_id} -> '{new_category}'.")
    try:
        success = update_transaction_category(transaction_id, new_category)
        if success:
            try:
                updated_tx = get_transaction_by_id(transaction_id)
                if updated_tx and updated_tx.description: save_user_rule(updated_tx.description, new_category); logging.info(f"Saved user rule for ID {transaction_id}.")
                else: logging.warning(f"Did not save user rule for ID {transaction_id} (no desc or fetch failed).")
            except Exception as rule_err: logging.error(f"Error saving user rule for ID {transaction_id}: {rule_err}", exc_info=True)
            return jsonify({"message": f"Transaction {transaction_id} category updated."}), 200
        else: abort(404, description=f"Transaction ID {transaction_id} not found.")
    except NotFound as e: raise e
    except Exception as e: logging.error(f"Error updating category for ID {transaction_id}: {e}", exc_info=True); abort(500)

@app.route('/transactions/<int:transaction_id>/set_category', methods=['GET'])
def update_category_get(transaction_id):
    # ... (GET update logic - unchanged) ...
    logging.info(f"'/transactions/{transaction_id}/set_category' (GET).")
    new_category = request.args.get('category')
    if not new_category or not isinstance(new_category, str) or not new_category.strip(): return "<h1>Bad Request</h1><p>Missing 'category' query parameter.</p>", 400
    new_category = new_category.strip()
    logging.info(f"Attempting GET update ID {transaction_id} -> '{new_category}'.")
    try:
        success = update_transaction_category(transaction_id, new_category)
        if success:
            try:
                updated_tx = get_transaction_by_id(transaction_id)
                if updated_tx and updated_tx.description: save_user_rule(updated_tx.description, new_category); logging.info(f"Saved user rule for ID {transaction_id}.")
                else: logging.warning(f"Did not save user rule for ID {transaction_id} (no desc or fetch failed).")
            except Exception as rule_err: logging.error(f"Error saving user rule for ID {transaction_id}: {rule_err}", exc_info=True)
            return f"<h1>Success</h1><p>Transaction {transaction_id} category updated to '{new_category.title()}'.</p>", 200
        else: return f"<h1>Not Found</h1><p>Transaction ID {transaction_id} not found.</p>", 404
    except Exception as e: logging.error(f"Error updating category ID {transaction_id}: {e}", exc_info=True); return f"<h1>Error</h1><p>{e}</p>", 500

@app.route('/trends/monthly_spending', methods=['GET'])
def get_monthly_spending_trends():
    # ... (trends logic - unchanged) ...
    logging.info("'/trends/monthly_spending' called.")
    try:
        all_db_transactions = get_all_transactions()
        logging.info(f"Fetched {len(all_db_transactions)} for trends.")
        if not all_db_transactions: return jsonify({"message": "No transactions available."}), 404
        trends_data = calculate_monthly_trends(all_db_transactions)
        logging.info("Trend calculation complete.")
        if "error" in trends_data: return jsonify(trends_data), 400
        return jsonify(trends_data)
    except Exception as e: logging.error(f"Error calculating trends: {e}", exc_info=True); abort(500)

@app.route('/recurring', methods=['GET'])
def get_recurring_transactions():
    # ... (recurring logic - unchanged) ...
    logging.info("'/recurring' called.")
    try: min_occurrences = int(request.args.get('min_occurrences', 3)); days_tolerance = int(request.args.get('days_tolerance', 3)); amount_tolerance_percent = float(request.args.get('amount_tolerance_percent', 5.0))
    except ValueError: abort(400, description="Invalid threshold parameter(s).")
    logging.info(f"Recurring thresholds: min={min_occurrences}, days={days_tolerance}, amount%={amount_tolerance_percent}")
    try:
        all_db_transactions = get_all_transactions()
        logging.info(f"Fetched {len(all_db_transactions)} for recurring.")
        if not all_db_transactions: return jsonify([])
        recurring_data = identify_recurring_transactions(all_db_transactions, min_occurrences=min_occurrences, days_tolerance=days_tolerance, amount_tolerance_percent=amount_tolerance_percent)
        logging.info(f"Identified {len(recurring_data)} recurring groups.")
        return jsonify(recurring_data)
    except Exception as e: logging.error(f"Error identifying recurring: {e}", exc_info=True); abort(500)

@app.route('/analysis/frequent_spending', methods=['GET'])
def get_frequent_spending():
    # ... (frequent spending logic - unchanged) ...
    logging.info("'/analysis/frequent_spending' endpoint called.")
    start_date_str = request.args.get('start_date'); end_date_str = request.args.get('end_date'); min_freq_str = request.args.get('min_frequency', '2')
    start_date, end_date = None, None; min_frequency = 2
    if start_date_str:
        try: start_date = dt.date.fromisoformat(start_date_str)
        except ValueError: abort(400, description="Invalid start_date format.")
    if end_date_str:
        try: end_date = dt.date.fromisoformat(end_date_str)
        except ValueError: abort(400, description="Invalid end_date format.")
    min_frequency_val = None
    try: min_frequency_val = int(min_freq_str)
    except ValueError: logging.warning(f"Invalid min_frequency parameter '{min_freq_str}'."); abort(400, description="Invalid min_frequency parameter.")
    if min_frequency_val < 1: logging.warning(f"min_frequency parameter must be >= 1, got {min_frequency_val}"); abort(400, description="min_frequency parameter must be at least 1.")
    min_frequency = min_frequency_val
    logging.info(f"Frequent spending params: start={start_date}, end={end_date}, min_freq={min_frequency}")
    try:
        all_db_transactions = get_all_transactions()
        logging.info(f"Fetched {len(all_db_transactions)} for frequent spending.")
        if not all_db_transactions: return jsonify([])
        frequent_data = analyze_frequent_spending(all_db_transactions, start_date=start_date, end_date=end_date, min_frequency=min_frequency)
        logging.info(f"Identified {len(frequent_data)} frequent spending patterns.")
        return jsonify(frequent_data)
    except Exception as e: logging.error(f"Error analyzing frequent spending: {e}", exc_info=True); abort(500)

@app.route('/analysis/duplicate_recurring', methods=['GET'])
def get_duplicate_recurring():
    # ... (duplicate recurring logic - unchanged) ...
    logging.info("'/analysis/duplicate_recurring' called.")
    try:
        min_occurrences = int(request.args.get('min_occurrences', 3)); days_tolerance = int(request.args.get('days_tolerance', 3)); amount_tolerance_percent = float(request.args.get('amount_tolerance_percent', 5.0))
        dup_amount_similarity = float(request.args.get('dup_amount_similarity', 10.0)); dup_max_days_apart = int(request.args.get('dup_max_days_apart', 7))
    except ValueError: abort(400, description="Invalid threshold parameter(s).")
    logging.info(f"Duplicate check using: rec_min={min_occurrences}, rec_days={days_tolerance}, rec_amt%={amount_tolerance_percent}, dup_amt%={dup_amount_similarity}, dup_days={dup_max_days_apart}")
    try:
        all_db_transactions = get_all_transactions()
        logging.info(f"Fetched {len(all_db_transactions)} for duplicate recurring.")
        if not all_db_transactions: return jsonify([])
        recurring_items = identify_recurring_transactions(all_db_transactions, min_occurrences=min_occurrences, days_tolerance=days_tolerance, amount_tolerance_percent=amount_tolerance_percent)
        logging.info(f"Identified {len(recurring_items)} recurring items to check.")
        if not recurring_items: return jsonify([])
        duplicate_data = find_potential_duplicate_recurring(recurring_items, amount_similarity_percent=dup_amount_similarity, max_days_apart_in_month=dup_max_days_apart)
        logging.info(f"Identified {len(duplicate_data)} potential duplicate groups.")
        return jsonify(duplicate_data)
    except Exception as e: logging.error(f"Error finding duplicate recurring: {e}", exc_info=True); abort(500)

@app.route('/analysis/llm_summary', methods=['GET'])
def get_llm_summary():
    # ... (LLM summary logic with date filtering - unchanged) ...
    logging.info("'/analysis/llm_summary' endpoint called.")
    start_date_str = request.args.get('start_date'); end_date_str = request.args.get('end_date')
    start_date, end_date = None, None
    if start_date_str:
        try: start_date = dt.date.fromisoformat(start_date_str)
        except ValueError: abort(400, description="Invalid start_date format.")
    if end_date_str:
        try: end_date = dt.date.fromisoformat(end_date_str)
        except ValueError: abort(400, description="Invalid end_date format.")
    if not start_date or not end_date:
        today = dt.date.today(); first_of_current_month = today.replace(day=1)
        default_end_date = first_of_current_month - relativedelta(days=1)
        default_start_date = first_of_current_month - relativedelta(months=3)
        if not start_date: start_date = default_start_date
        if not end_date: end_date = default_end_date
        logging.info(f"Using date range for LLM summary: {start_date.isoformat()} to {end_date.isoformat()} (Default or Provided)")
    else: logging.info(f"Using provided date range for LLM summary: {start_date.isoformat()} to {end_date.isoformat()}")
    start_date_query_str = start_date.isoformat(); end_date_query_str = end_date.isoformat()
    try:
        transactions_for_period = get_all_transactions(start_date=start_date_query_str, end_date=end_date_query_str)
        logging.info(f"Fetched {len(transactions_for_period)} transactions for LLM analysis period.")
        if not transactions_for_period: return jsonify({"summary": f"No transaction data found for the period {start_date_query_str} to {end_date_query_str}."}), 404
        summary_data = calculate_summary_insights(transactions_for_period)
        trends_data = calculate_monthly_trends(transactions_for_period)
        logging.info("Generated necessary data for LLM summary based on filtered period.")
        llm_summary_text = generate_financial_summary(summary_data, trends_data, start_date_query_str, end_date_query_str)
        if llm_summary_text.startswith("Error:"):
             status_code = 503 if "API error" in llm_summary_text or "not configured" in llm_summary_text else 500
             return jsonify({"error": llm_summary_text}), status_code
        logging.info("LLM summary generated successfully.")
        return jsonify({"summary": llm_summary_text})
    except Exception as e: logging.error(f"Error generating LLM summary: {e}", exc_info=True); abort(500)


# --- Change: Update /ask Endpoint ---
@app.route('/ask', methods=['GET'])
def ask_llm_question():
    """Answers a user's financial question using the LLM and transaction data."""
    logging.info("'/ask' endpoint called.")
    question = request.args.get('query')
    if not question or not isinstance(question, str) or not question.strip():
        abort(400, description="Missing or invalid 'query' parameter.")

    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    start_date, end_date = None, None
    user_provided_dates = False

    if start_date_str:
        try: start_date = dt.date.fromisoformat(start_date_str); user_provided_dates = True
        except ValueError: abort(400, description="Invalid start_date format.")
    if end_date_str:
        try: end_date = dt.date.fromisoformat(end_date_str); user_provided_dates = True
        except ValueError: abort(400, description="Invalid end_date format.")

    # --- Change: Intelligent Date Filtering (Default to 2 years if no dates) ---
    if not user_provided_dates:
        year_match = re.search(r'\b(20\d{2})\b', question)
        month_match = re.search(r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\b', question, re.IGNORECASE)
        # Add more sophisticated date parsing here if needed

        if year_match:
            year = int(year_match.group(1))
            # If month also mentioned, scope to that month? For now, year takes precedence
            start_date = dt.date(year, 1, 1); end_date = dt.date(year, 12, 31)
            start_date_str = start_date.isoformat(); end_date_str = end_date.isoformat()
            logging.info(f"Detected year {year}, setting range: {start_date_str} to {end_date_str}")
        # --- Change: Default to last 2 years if no specific range detected ---
        else:
            today = dt.date.today()
            start_date = today - relativedelta(years=2)
            end_date = today # Include today
            start_date_str = start_date.isoformat(); end_date_str = end_date.isoformat()
            logging.info(f"No specific date range detected/provided for Q&A. Defaulting to last 2 years: {start_date_str} to {end_date_str}")
        # --- End Change ---

    logging.info(f"Received question: '{question}'. Fetching data from {start_date_str or 'start'} to {end_date_str or 'end'}")

    try:
        # Fetch transactions using the determined date range
        transactions_for_llm = get_all_transactions(start_date=start_date, end_date=end_date)
        logging.info(f"Fetched {len(transactions_for_llm)} transactions for question context.")

        if not transactions_for_llm:
             if start_date or end_date: return jsonify({"answer": f"I couldn't find any transactions between {start_date_str or 'start'} and {end_date_str or 'end'}."}), 404
             else: return jsonify({"answer": "There are no transactions loaded."}), 404

        # Calculate summary for the fetched period
        summary_data_for_period = calculate_summary_insights(transactions_for_llm)
        logging.info("Calculated summary data for the relevant period for Q&A.")

        # Call the LLM service function, passing summary and transactions
        llm_answer = answer_financial_question(
            question,
            transactions_for_llm,
            summary_data_for_period,
            start_date_str,
            end_date_str
        )

        if llm_answer.startswith("Error:"):
            status_code = 503 if "API error" in llm_answer or "not configured" in llm_answer else 500
            return jsonify({"error": llm_answer}), status_code

        logging.info("LLM answer generated successfully.")
        return jsonify({"question": question, "answer": llm_answer})

    except Exception as e:
        logging.error(f"Error answering question '{question}': {e}", exc_info=True)
        abort(500, description="Internal server error answering question.")
# --- End Change ---


# --- Main Execution ---
if __name__ == '__main__':
    logging.info("Initializing database...")
    init_db()
    if not os.path.exists(UPLOAD_FOLDER): os.makedirs(UPLOAD_FOLDER)
    app.run(debug=True, port=5001)


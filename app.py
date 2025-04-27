import os
import json
import logging
from pathlib import Path
from werkzeug.exceptions import NotFound, BadRequest
from flask import Flask, request, jsonify, abort
from werkzeug.utils import secure_filename
from decimal import Decimal

# Imports remain the same
from parser import Transaction, parse_checking_csv, parse_credit_csv
# Change: Import the new trends function
from insights import calculate_summary_insights, calculate_monthly_trends
from database import (
    init_db, add_transactions, get_all_transactions,
    update_transaction_category, save_user_rule,
    get_transaction_by_id, DATABASE_FILE
)

# Configuration remains the same
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [APP] %(message)s')
app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'csv'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
Path(UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)

# Helper Functions & JSON Encoder remain the same
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal): return str(obj)
        # Handle float('inf') for JSON compatibility
        if obj == float('inf'): return "Infinity" # Or None, or a large number string
        if obj == float('-inf'): return "-Infinity"
        return super(DecimalEncoder, self).default(obj)
app.json_encoder = DecimalEncoder

# --- Flask Routes ---
# index, upload, transactions, summary, update_category_put, update_category_get routes remain the same
@app.route('/')
def index():
    if not DATABASE_FILE.exists(): init_db()
    return "SpendLens Backend is running! Database is ready."

@app.route('/upload', methods=['POST'])
def upload_files():
    # ... (upload logic as before) ...
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
                    file.save(str(file_path))
                    logging.info(f"File '{filename}' saved successfully.")
                    parsed_txs = []
                    if 'checking' in filename.lower(): parsed_txs = parse_checking_csv(file_path)
                    elif 'credit' in filename.lower(): parsed_txs = parse_credit_csv(file_path)
                    else: errors.append(f"Could not determine parser for file: {filename}")
                    if parsed_txs: newly_parsed_transactions.extend(parsed_txs); logging.info(f"Parsed {len(parsed_txs)} transactions from {filename}.")
                    elif not any(e.startswith(f"Could not determine parser for file: {filename}") for e in errors): errors.append(f"No transactions parsed or error during parsing for {filename}.")
                except Exception as e:
                    errors.append(f"Error processing file {filename}: {str(e)}")
                    logging.error(f"Error processing file {filename}: {e}", exc_info=True)
                finally:
                    if file_path.exists():
                        try: os.remove(file_path); logging.info(f"Removed temporary file: {file_path}")
                        except OSError as remove_err: logging.error(f"Error removing temporary file {file_path}: {remove_err}")
            elif file: errors.append(f"File type not allowed for {file.filename}")
    if uploaded_files_count == 0 and not errors: abort(400, description="No valid CSV files were uploaded.")
    total_parsed = len(newly_parsed_transactions)
    logging.info(f"Parsing complete. Attempting to save {total_parsed} transactions to database (clear_existing=True).")
    db_save_error = None
    try:
        add_transactions(newly_parsed_transactions, clear_existing=True)
        logging.info(f"Database save operation completed.")
    except Exception as db_err:
        db_save_error = f"Database error saving transactions: {str(db_err)}"
        errors.append(db_save_error); logging.error(f"Database error saving transactions: {db_err}", exc_info=True); total_parsed = 0
    response_data = {"message": f"Processed {uploaded_files_count} file(s). Saved {total_parsed} new transactions to database.", "errors": errors}
    status_code = 200 if db_save_error is None else 500
    if status_code == 200 and errors: status_code = 207
    return jsonify(response_data), status_code

@app.route('/transactions', methods=['GET'])
def get_transactions():
    logging.info("'/transactions' endpoint called. Fetching from DB...")
    try:
        all_db_transactions = get_all_transactions()
        transactions_dict_list = [tx.to_dict() for tx in all_db_transactions]
        logging.info(f"Returning {len(transactions_dict_list)} transactions.")
        return jsonify(transactions_dict_list)
    except Exception as e:
        logging.error(f"Error retrieving transactions from database: {e}", exc_info=True)
        abort(500, description="Internal server error retrieving transactions.")

@app.route('/summary', methods=['GET'])
def get_summary():
    logging.info("'/summary' endpoint called. Fetching from DB...")
    try:
        all_db_transactions = get_all_transactions()
        logging.info(f"Fetched {len(all_db_transactions)} transactions for summary.")
        if not all_db_transactions:
            logging.info("No transactions found in DB for summary.")
            return jsonify({"message": "No transactions found in database."}), 404
        summary_data = calculate_summary_insights(all_db_transactions)
        logging.info("Summary calculation complete. Returning summary.")
        return jsonify(summary_data)
    except Exception as e:
        logging.error(f"Error calculating summary from database data: {e}", exc_info=True)
        abort(500, description="Internal server error calculating summary.")

@app.route('/transactions/<int:transaction_id>/category', methods=['PUT'])
def update_category_put(transaction_id):
    logging.info(f"'/transactions/{transaction_id}/category' endpoint called (PUT).")
    raw_data = request.data; logging.info(f"DEBUG: Raw request data received: {raw_data}")
    if not request.is_json: abort(400, description=f"Request body must be JSON.")
    try:
        data = request.get_json();
        if data is None: abort(400, description="Failed to decode JSON object.")
    except BadRequest as e: raise e
    if 'category' not in data or not isinstance(data['category'], str) or not data['category'].strip(): abort(400, description="Missing or invalid 'category' field in JSON body.")
    new_category = data['category'].strip()
    logging.info(f"Attempting PUT update for ID {transaction_id} with new category '{new_category}'.")
    try:
        success = update_transaction_category(transaction_id, new_category)
        if success:
            try:
                updated_tx = get_transaction_by_id(transaction_id)
                if updated_tx and updated_tx.description: save_user_rule(updated_tx.description, new_category); logging.info(f"Attempted to save user rule for ID {transaction_id}.")
                elif updated_tx: logging.warning(f"Could not save user rule for ID {transaction_id} because description was empty.")
                else: logging.warning(f"Could not fetch transaction {transaction_id} after update to save user rule.")
            except Exception as rule_err: logging.error(f"Error saving user rule for ID {transaction_id}: {rule_err}", exc_info=True)
            return jsonify({"message": f"Transaction {transaction_id} category updated successfully."}), 200
        else: abort(404, description=f"Transaction with ID {transaction_id} not found.")
    except NotFound as e: raise e
    except Exception as e: logging.error(f"Error updating category for ID {transaction_id}: {e}", exc_info=True); abort(500, description="Internal server error updating transaction category.")

@app.route('/transactions/<int:transaction_id>/set_category', methods=['GET'])
def update_category_get(transaction_id):
    logging.info(f"'/transactions/{transaction_id}/set_category' endpoint called (GET).")
    new_category = request.args.get('category')
    if not new_category or not isinstance(new_category, str) or not new_category.strip(): return "<h1>Bad Request</h1><p>Missing or invalid 'category' query parameter.</p>", 400
    new_category = new_category.strip()
    logging.info(f"Attempting GET update for ID {transaction_id} with new category '{new_category}'.")
    try:
        success = update_transaction_category(transaction_id, new_category)
        if success:
            try:
                updated_tx = get_transaction_by_id(transaction_id)
                if updated_tx and updated_tx.description: save_user_rule(updated_tx.description, new_category); logging.info(f"Attempted to save user rule for ID {transaction_id}.")
                elif updated_tx: logging.warning(f"Could not save user rule for ID {transaction_id} because description was empty.")
                else: logging.warning(f"Could not fetch transaction {transaction_id} after update to save user rule.")
            except Exception as rule_err: logging.error(f"Error saving user rule for ID {transaction_id}: {rule_err}", exc_info=True)
            return f"<h1>Success</h1><p>Transaction {transaction_id} category updated to '{new_category.title()}'. User rule potentially saved.</p>", 200
        else: return f"<h1>Not Found</h1><p>Transaction with ID {transaction_id} not found.</p>", 404
    except Exception as e: logging.error(f"Error updating category for ID {transaction_id}: {e}", exc_info=True); return f"<h1>Internal Server Error</h1><p>An error occurred: {e}</p>", 500


# --- Change: Add Monthly Trends Endpoint ---
@app.route('/trends/monthly_spending', methods=['GET'])
def get_monthly_spending_trends():
    """
    Retrieves transactions from DB, calculates monthly spending trends,
    and returns the analysis.
    """
    logging.info("'/trends/monthly_spending' endpoint called. Fetching from DB...")
    try:
        # 1. Fetch all transactions
        all_db_transactions = get_all_transactions()
        logging.info(f"Fetched {len(all_db_transactions)} transactions for trend analysis.")

        if not all_db_transactions:
            logging.info("No transactions found in DB for trend analysis.")
            # Return 404 if no data exists at all
            return jsonify({"message": "No transactions available to calculate trends."}), 404

        # 2. Calculate trends using the function from insights.py
        trends_data = calculate_monthly_trends(all_db_transactions)
        logging.info("Monthly trend calculation complete.")

        # 3. Check for errors from the trends function (e.g., insufficient data)
        if "error" in trends_data:
            logging.warning(f"Trend calculation returned an error: {trends_data['error']}")
            # Return a 400 Bad Request or similar if not enough data
            return jsonify(trends_data), 400 # Use 400 for insufficient data error

        # 4. Return the successful trend data
        # jsonify will use the app's DecimalEncoder
        return jsonify(trends_data)

    except Exception as e:
        logging.error(f"Error calculating monthly trends: {e}", exc_info=True)
        abort(500, description="Internal server error calculating monthly trends.")


# --- Main Execution ---
if __name__ == '__main__':
    logging.info("Initializing database...")
    init_db()
    if not os.path.exists(UPLOAD_FOLDER): os.makedirs(UPLOAD_FOLDER)
    app.run(debug=True, port=5001)

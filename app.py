import os
import logging
import re # Import regular expressions
import string # For punctuation removal
from flask import (
    Flask, request, jsonify, render_template, redirect, url_for,
    send_from_directory, flash, session
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import datetime as dt
from dateutil.relativedelta import relativedelta
from dateutil.parser import parse as dateutil_parse, ParserError # For parsing flexible date strings
from decimal import Decimal, InvalidOperation
from typing import Optional, List, Dict, Any, Tuple, Union
import io # For processing files in memory

# --- Flask Extension Imports ---
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user

# --- Project Specific Imports (Ensure these match your project structure) ---
import database_supabase # Assuming database_supabase.py handles User model and db interactions
import parser # parser.py now has the new schema-based parsers
import insights
import llm_service
from config import Config

# --- Flask App Setup ---
app = Flask(__name__, static_folder='../frontend/dist', static_url_path='/')
app.config.from_object(Config)

# --- Configure Logging ---
log = logging.getLogger('app')
log.setLevel(logging.INFO)
if not log.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s:%(funcName)s] - %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)

# --- Initialize Flask Extensions ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Or React equivalent if no Flask login page
login_manager.login_message_category = 'info'

# --- Ensure Upload Folder Exists ---
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])
    log.info(f"Created upload folder: {app.config['UPLOAD_FOLDER']}")

# --- Database Initialization ---
try:
    database_supabase.initialize_database()
    log.info("Database initialized successfully.")
except Exception as e:
    log.critical(f"Failed to initialize database on startup: {e}", exc_info=True)

# --- User Loader for Flask-Login ---
@login_manager.user_loader
def load_user(user_id):
    log.debug(f"Attempting to load user with ID: {user_id}")
    user = database.find_user_by_id(int(user_id))
    if user:
        log.debug(f"User {user_id} loaded successfully: {user.username}")
        return user
    log.warning(f"No user found for ID: {user_id}")
    return None

# --- Helper Functions ---
def allowed_file(filename: str) -> bool:
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def parse_date_param(date_str: Optional[str], default: Optional[dt.date]) -> Optional[dt.date]:
    if not date_str: return default
    try:
        return dt.datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        log.warning(f"Invalid date format received: '{date_str}'. Using default: {default}")
        return default

def parse_dates_from_query(query: str) -> Optional[Union[Tuple[dt.date, dt.date], dt.date]]:
    # (Keep your existing date parsing logic from the query)
    # This function seems complete and well-tested based on previous versions.
    # For brevity, I'm not reproducing the full logic here but it should remain.
    q_lower = query.lower()
    today = dt.date.today()
    current_year = today.year
    month_pattern = r'\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b'

    try:
        specific_date_match = re.search(r'\b(?:on\s+|date\s+)?(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|' + month_pattern + r'\s+\d{1,2}(?:st|nd|rd|th)?(?:,\s*\d{4})?)\b', q_lower)
        if specific_date_match:
             date_str_to_parse = specific_date_match.group(1)
             log.debug(f"Potential single date string found: '{date_str_to_parse}'")
             is_likely_just_month = re.fullmatch(month_pattern, date_str_to_parse.strip())
             if not is_likely_just_month:
                 parsed_dt = dateutil_parse(date_str_to_parse, fuzzy=False)
                 specific_date = parsed_dt.date()
                 if parsed_dt.year >= 1990 and (parsed_dt.year != current_year or str(current_year) in date_str_to_parse or re.search(r'\b\d{1,2}(?:st|nd|rd|th)\b', date_str_to_parse)):
                     log.info(f"Parsed specific single date from query: {specific_date}")
                     return specific_date
                 else: log.debug("Parsed date seemed ambiguous, continuing...")
    except (ParserError, ValueError, OverflowError, TypeError, AttributeError) as e:
         log.debug(f"Dateutil parsing for single date failed or was ambiguous: {e}")
         pass

    month_this_year_match = re.search(f'({month_pattern})\\s+this\\s+year', q_lower)
    if month_this_year_match:
        month_str = month_this_year_match.group(1)
        try:
            month_dt = dateutil_parse(f"{month_str} 1, {current_year}"); month = month_dt.month
            start_date = dt.date(current_year, month, 1)
            end_date = (start_date + relativedelta(months=1)) - dt.timedelta(days=1)
            log.info(f"Parsed 'month this year' range: {start_date} to {end_date}")
            return start_date, end_date
        except (ValueError, OverflowError) as e: log.warning(f"Could not parse month for 'month this year': {e}")

    month_year_match = re.search(f'({month_pattern})\\s+(\\d{{4}})', q_lower)
    if month_year_match:
        month_str, year_str = month_year_match.groups(); year = int(year_str)
        try:
            month_dt = dateutil_parse(f"{month_str} 1, {year}"); month = month_dt.month
            start_date = dt.date(year, month, 1)
            end_date = (start_date + relativedelta(months=1)) - dt.timedelta(days=1)
            log.info(f"Parsed 'month year' range: {start_date} to {end_date}")
            return start_date, end_date
        except (ValueError, OverflowError) as e: log.warning(f"Could not parse month/year '{month_str} {year_str}': {e}")

    standalone_month_match = re.search(f'({month_pattern})(?!\\s*(?:this\\s+year|\\d))', q_lower)
    if standalone_month_match:
         month_str = standalone_month_match.group(1)
         if not (month_year_match and month_year_match.group(1) == month_str) and \
            not (month_this_year_match and month_this_year_match.group(1) == month_str):
             try:
                month_dt = dateutil_parse(f"{month_str} 1, {current_year}")
                month = month_dt.month
                start_date = dt.date(current_year, month, 1)
                end_date = (start_date + relativedelta(months=1)) - dt.timedelta(days=1)
                log.info(f"Parsed standalone month '{month_str}' (current year): {start_date} to {end_date}")
                return start_date, end_date
             except (ValueError, OverflowError) as e:
                log.warning(f"Could not parse standalone month '{month_str}': {e}")

    if "last month" in q_lower:
        end_of_last_month = today.replace(day=1) - dt.timedelta(days=1)
        start_of_last_month = end_of_last_month.replace(day=1)
        log.info(f"Parsed 'last month' range: {start_of_last_month} to {end_of_last_month}")
        return start_of_last_month, end_of_last_month
    if "this month" in q_lower:
        start_of_this_month = today.replace(day=1)
        end_of_this_month = today
        log.info(f"Parsed 'this month' range: {start_of_this_month} to {end_of_this_month}")
        return start_of_this_month, end_of_this_month
    if not month_year_match and not month_this_year_match and not standalone_month_match:
        year_match = re.search(r'\b(in|for|during)\s+(\d{4})\b|\b(\d{4})\b', q_lower)
        if year_match:
            year_str = year_match.group(2) or year_match.group(3)
            try:
                year = int(year_str)
                if 1990 < year <= current_year + 1:
                    start_date = dt.date(year, 1, 1); end_date = dt.date(year, 12, 31)
                    log.info(f"Parsed 'year' range: {start_date} to {end_date}")
                    return start_date, end_date
            except ValueError: log.warning(f"Could not parse year from '{year_str}'")
    if "this year" in q_lower and not month_this_year_match and not standalone_month_match:
        start_date = dt.date(current_year, 1, 1); end_date = dt.date(current_year, 12, 31)
        log.info(f"Parsed 'this year' range: {start_date} to {end_date}")
        return start_date, end_date
    if "last year" in q_lower:
        year = current_year - 1; start_date = dt.date(year, 1, 1); end_date = dt.date(year, 12, 31)
        log.info(f"Parsed 'last year' range: {start_date} to {end_date}")
        return start_date, end_date
    log.debug(f"No specific date or range parsed from query: '{query}'")
    return None

# --- Routes ---

# Serve React App Entry Point and Static Files
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_react_app(path):
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    index_path = os.path.join(app.static_folder, 'index.html')
    if os.path.exists(index_path):
        return send_from_directory(app.static_folder, 'index.html')
    log.error(f"React build index.html not found at {index_path}")
    return "Frontend application not found. Please build the React app.", 404

# --- API Routes for React Frontend ---
@app.route('/api/login', methods=['POST'])
def api_login():
    # (Keep existing API login logic)
    log.debug("Received request for /api/login")
    if current_user.is_authenticated:
        return jsonify({"message": "Already logged in.", "user_id": current_user.id, "username": current_user.username}), 200
    if not request.is_json:
        return jsonify({"message": "Request must be JSON"}), 400
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({"message": "Username and password are required"}), 400
    log.debug(f"Attempting API login for username: {username}")
    user = database_supabase.find_user_by_username(username)
    if user and check_password_hash(user.password_hash, password):
        login_user(user, remember=True)
        log.info(f"User '{user.username}' logged in successfully via API.")
        return jsonify({"message": "Login successful", "user_id": user.id, "username": user.username}), 200
    log.warning(f"API Login failed for username: {username}")
    return jsonify({"message": "Invalid username or password"}), 401

@app.route('/api/logout', methods=['POST'])
@login_required
def api_logout():
    # (Keep existing API logout logic)
    log.info(f"User '{current_user.username}' logging out via API.")
    logout_user()
    return jsonify({"message": "Logout successful"}), 200

@app.route('/api/register', methods=['POST'])
def api_register():
    # (Keep existing API register logic)
    log.debug("Received request for /api/register")
    if current_user.is_authenticated:
        return jsonify({"message": "Already logged in"}), 400
    if not request.is_json:
        return jsonify({"message": "Request must be JSON"}), 400
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({"message": "Username and password are required"}), 400
    if database.find_user_by_username(username):
        return jsonify({"message": "Username already exists"}), 409
    hashed_password = generate_password_hash(password)
    user_id = database_supabase.create_user(username, hashed_password)
    if user_id:
        log.info(f"User '{username}' registered successfully via API.")
        return jsonify({"message": "Registration successful. Please log in.", "user_id": user_id, "username": username}), 201
    log.error(f"API registration failed for username '{username}'.")
    return jsonify({"message": "Registration failed. Please try again."}), 500

@app.route('/api/check_auth', methods=['GET'])
def check_auth_status():
    # (Keep existing auth check logic)
    if current_user.is_authenticated:
        log.debug(f"Auth check API: User {current_user.username} is authenticated.")
        return jsonify({"isAuthenticated": True, "user": {"id": current_user.id, "username": current_user.username}}), 200
    log.debug("Auth check API: No user authenticated.")
    return jsonify({"isAuthenticated": False, "user": None}), 200

# --- Protected Data API Routes (Require Login) ---

@app.route('/api/upload', methods=['POST'])
@login_required
def api_upload_file():
    """
    Handles file uploads via API for the logged-in user.
    Supports various CSV formats (Chase, Stripe, PayPal, Invoices).
    """
    user_id = current_user.id
    log.info(f"User {user_id}: API Upload request received.")

    # Define which file keys map to which parser functions
    # This could be expanded or made more dynamic
    # The keys (e.g., 'checking_file') must match the 'name' attribute of the <input type="file"> in the frontend form.
    parser_map = {
        'checking_file': parser.parse_checking_csv,
        'credit_file': parser.parse_credit_csv,
        'stripe_file': parser.parse_stripe_csv,
        'paypal_file': parser.parse_paypal_csv,
        'invoice_file': parser.parse_invoice_csv,
        # Add more mappings here for other file types like time logs
        # 'togl_file': parser.parse_togl_csv,
    }

    # Check if any of the expected file keys are present
    if not any(key in request.files for key in parser_map.keys()):
        log.warning(f"User {user_id}: No file part found in the request. Expected one of: {list(parser_map.keys())}")
        return jsonify({"message": "No file part in the request. Ensure the file input name is correct."}), 400

    files_processed_names: List[str] = []
    all_transactions: List[parser.Transaction] = [] # Use parser.Transaction type hint
    errors: List[str] = []

    # It's generally a good idea to clear previous data for a new bulk upload session.
    # Consider if this should be optional or handled differently for appending data.
    try:
        database_supabase.clear_transactions_for_user(user_id)
        database_supabase.clear_llm_rules_for_user(user_id) # Also clear old LLM suggestions
        log.info(f"User {user_id}: Cleared previous transaction and LLM rule data.")
    except Exception as e:
        log.error(f"User {user_id}: Error clearing data: {e}", exc_info=True)
        return jsonify({"message": "Failed to prepare for upload. Please try again."}), 500

    # Process each expected file type
    for file_key, parser_function in parser_map.items():
        file_obj = request.files.get(file_key)
        if file_obj and file_obj.filename and allowed_file(file_obj.filename):
            original_filename = secure_filename(file_obj.filename)
            log.info(f"User {user_id}: Processing uploaded file '{original_filename}' for key '{file_key}'.")

            # The parser functions now expect a file-like object (BytesIO or TextIO)
            # and the original filename.
            # We read the file into BytesIO here. parser.py's _get_text_stream will wrap it.
            file_stream = io.BytesIO(file_obj.read())
            file_obj.close() # Close the original file object from Flask

            try:
                # TODO: Future - Receive schema from frontend if per-column mapping is implemented.
                # custom_schema_json = request.form.get(f"{file_key}_schema")
                # if custom_schema_json:
                #     custom_schema = json.loads(custom_schema_json)
                #     txns = parser_function(user_id, file_stream, original_filename, schema=custom_schema)
                # else:
                #     txns = parser_function(user_id, file_stream, original_filename) # Relies on default schema in parser

                # Current implementation: parser functions use their predefined schemas
                txns = parser_function(user_id=user_id, file_obj=file_stream, filename=original_filename)

                all_transactions.extend(txns)
                files_processed_names.append(original_filename)
                log.info(f"User {user_id}: Parsed {len(txns)} transactions from '{original_filename}'.")
            except ValueError as ve: # Catch specific parsing errors (e.g., missing columns)
                log.error(f"User {user_id}: Parsing error for '{original_filename}': {ve}")
                errors.append(f"Error processing file '{original_filename}': {str(ve)}")
            except RuntimeError as rte: # Catch runtime errors from parser (e.g., unexpected failures)
                log.error(f"User {user_id}: Runtime error processing '{original_filename}': {rte}")
                errors.append(f"Critical error processing file '{original_filename}'.")
            except Exception as e:
                log.error(f"User {user_id}: Unexpected error processing file '{original_filename}': {e}", exc_info=True)
                errors.append(f"Unexpected error with file '{original_filename}': {str(e)}")
            finally:
                if file_stream: # Ensure BytesIO stream is closed
                    file_stream.close()
        elif file_obj and file_obj.filename and not allowed_file(file_obj.filename):
            log.warning(f"User {user_id}: File '{file_obj.filename}' has a disallowed extension.")
            errors.append(f"File type not allowed for '{file_obj.filename}'. Please upload a CSV file.")


    saved_count = 0
    if all_transactions and not any("critical error" in err.lower() for err in errors): # Avoid saving if critical parsing failed
        try:
            database_supabase.save_transactions(user_id, all_transactions)
            saved_count = len(all_transactions)
            log.info(f"User {user_id}: Saved {saved_count} transactions to database.")
        except Exception as e:
            log.error(f"User {user_id}: Error saving transactions: {e}", exc_info=True)
            errors.append("Database save error: Failed to store transaction data.")
            saved_count = 0 # Reset count on save failure

    llm_suggestions_count = 0
    if saved_count > 0: # Only run LLM if transactions were successfully saved
        try:
            log.info(f"User {user_id}: Starting LLM category suggestion for newly uploaded transactions...")
            uncategorized_tx = [tx for tx in all_transactions if tx.category == 'Uncategorized']
            log.info(f"User {user_id}: Found {len(uncategorized_tx)} uncategorized transactions for LLM.")
            if uncategorized_tx:
                # Define valid categories for business context (can be expanded)
                # TODO: These categories should ideally be configurable per user or system-wide for business use.
                valid_categories = [
                    "Revenue", "Software Subscription", "Contractor Payment", "Office Supplies",
                    "Travel Expense", "Meals & Entertainment", "Utilities", "Rent/Lease",
                    "Advertising & Marketing", "Professional Fees", "Bank Fees", "Hardware",
                    "Shipping & Postage", "Salaries & Wages", "Taxes", "Insurance",
                    "Client Refund", "Payout", "Platform Fee", "Other Income", "Other Expense",
                    "Ignore", "Uncategorized"
                ]
                context_rules = {};
                if hasattr(parser, 'VENDOR_RULES'): context_rules.update(parser.VENDOR_RULES)
                user_specific_rules = database_supabase.get_user_rules(user_id);
                context_rules.update(user_specific_rules)
                log.debug(f"User {user_id}: Context rules for LLM: {list(context_rules.keys())[:5]}...")

                suggested_rules_map = llm_service.suggest_categories_for_transactions(
                    uncategorized_tx, valid_categories, context_rules
                )

                if suggested_rules_map:
                    log.info(f"User {user_id}: LLM provided {len(suggested_rules_map)} category suggestions. Saving...");
                    for desc_key, suggested_cat in suggested_rules_map.items():
                        try:
                            parser.save_llm_rule(user_id, desc_key, suggested_cat)
                            llm_suggestions_count += 1
                        except Exception as rule_save_err:
                            log.error(f"User {user_id}: Failed to save LLM rule '{desc_key}'->'{suggested_cat}': {rule_save_err}")
                            errors.append(f"Error saving AI suggestion for '{desc_key}'")
                    log.info(f"User {user_id}: Saved {llm_suggestions_count} LLM-suggested rules.")
                else:
                    log.info(f"User {user_id}: LLM provided no new category suggestions.")
            else:
                log.info(f"User {user_id}: No 'Uncategorized' transactions found for LLM processing.")
        except Exception as llm_error:
            log.error(f"User {user_id}: LLM suggestion process error: {llm_error}", exc_info=True)
            errors.append(f"AI Suggestion Error: {str(llm_error)}")

    # Construct final response message
    if not files_processed_names and not errors: # No files were actually processed
        return jsonify({"message": "No valid files were uploaded or processed. Please select CSV files."}), 400

    final_message = f"Processed {saved_count} transactions from {len(files_processed_names)} file(s)."
    if llm_suggestions_count > 0:
        final_message += f" Saved {llm_suggestions_count} AI category suggestions."

    if errors:
        # Determine final status code: 500 if core processing failed, 207 if some success with errors
        status_code = 500 if saved_count == 0 and any("Database" in e or "critical error" in e.lower() for e in errors) else 207
        return jsonify({"message": final_message + " Encountered errors.", "files_processed": files_processed_names, "errors": errors}), status_code
    else:
        return jsonify({"message": final_message, "files_processed": files_processed_names, "transactions_count": saved_count}), 201


@app.route('/api/transactions', methods=['GET'])
@login_required
def api_get_transactions():
    # (Keep existing transaction fetching logic)
    # Ensure Transaction.to_dict() in database_supabase.py or parser.py handles new fields if they are to be sent to frontend.
    user_id = current_user.id
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    category = request.args.get('category')
    # Optional: Add filter for transaction_origin if needed by frontend
    # transaction_origin_filter = request.args.get('transaction_origin')

    log.info(f"User {user_id}: /api/transactions request: start={start_date_str}, end={end_date_str}, category={category}")
    start_date_obj = parse_date_param(start_date_str, None)
    end_date_obj = parse_date_param(end_date_str, None)
    start_param = start_date_obj.isoformat() if start_date_obj else None
    end_param = end_date_obj.isoformat() if end_date_obj else None

    if start_date_obj and end_date_obj and start_date_obj > end_date_obj:
        return jsonify({"message": "Start date cannot be after end date."}), 400
    try:
        # Assuming database.get_all_transactions can handle the filters
        transactions = database_supabase.get_all_transactions(user_id, start_param, end_param, category)
        # The Transaction class in database_supabase.py should have a to_dict() that includes new fields
        # if they are to be sent to the frontend.
        transactions_dict = [tx.to_dict() for tx in transactions if hasattr(tx, 'to_dict')]
        log.info(f"User {user_id}: Returning {len(transactions_dict)} transactions via API.")
        return jsonify(transactions_dict)
    except Exception as e:
        log.error(f"User {user_id}: Error getting transactions via API: {e}", exc_info=True)
        return jsonify({"message": "Failed to retrieve transactions."}), 500


@app.route('/api/transactions/<int:transaction_id>/category', methods=['PUT'])
@login_required
def api_update_category(transaction_id):
    # (Keep existing category update logic)
    user_id = current_user.id
    if not request.is_json: return jsonify({"message": "Request must be JSON"}), 400
    data = request.get_json()
    new_category = data.get('category')
    if not new_category or not isinstance(new_category, str):
        return jsonify({"message": "Missing or invalid 'category' field"}), 400

    log.info(f"User {user_id}: API request to update category for Tx {transaction_id} to '{new_category}'")
    try:
        # Security: Verify transaction belongs to user before updating.
        # database.update_transaction_category should ideally handle this check.
        tx_to_update = database_supabase.get_transaction_by_id_for_user(user_id, transaction_id) # Assumes this function exists
        if not tx_to_update:
             log.warning(f"User {user_id}: Attempted to update non-existent or unauthorized Tx {transaction_id}")
             return jsonify({"message": "Transaction not found or access denied"}), 404

        success = database_supabase.update_transaction_category(user_id, transaction_id, new_category)
        if success:
            desc_for_rule = tx_to_update.raw_description or tx_to_update.description
            if desc_for_rule:
                try:
                    parser.add_user_rule(user_id, desc_for_rule, new_category)
                    log.info(f"User {user_id}: Saved user rule for desc '{desc_for_rule}' -> '{new_category}'.")
                except Exception as rule_save_err:
                    log.error(f"User {user_id}: Failed to save user rule for Tx {transaction_id}: {rule_save_err}")
            return jsonify({"message": f"Tx {transaction_id} category updated to '{new_category}'"}), 200
        else:
            log.error(f"User {user_id}: DB update failed for Tx {transaction_id} category.")
            return jsonify({"message": "Failed to update transaction category"}), 500
    except Exception as e:
        log.error(f"User {user_id}: Error updating category for Tx {transaction_id}: {e}", exc_info=True)
        return jsonify({"message": "An unexpected error occurred."}), 500

# --- Analysis API Endpoints ---
@app.route('/api/summary', methods=['GET'])
@login_required
def api_get_summary():
    # (Keep existing summary logic)
    # insights.calculate_summary_insights might need updates if business transactions
    # (e.g., payouts vs. client revenue) should be treated differently from consumer income/spending.
    user_id = current_user.id
    today = dt.date.today()
    default_end_date = today
    default_start_date = today - relativedelta(years=2)
    start_date_query = request.args.get('start_date')
    end_date_query = request.args.get('end_date')
    start_date = parse_date_param(start_date_query, default_start_date)
    end_date = parse_date_param(end_date_query, default_end_date)

    if start_date and end_date and start_date > end_date:
        return jsonify({"message": "Start date cannot be after end date."}), 400
    start_date_str = start_date.isoformat() if start_date else None
    end_date_str = end_date.isoformat() if end_date else None
    log.info(f"User {user_id}: API generating summary: {start_date_str} to {end_date_str}")
    try:
        transactions_for_period = database_supabase.get_all_transactions(user_id, start_date_str, end_date_str)
        if not transactions_for_period:
             return jsonify(insights.calculate_summary_insights([])) # Pass empty list
        summary_data = insights.calculate_summary_insights(transactions_for_period)
        return jsonify(summary_data)
    except Exception as e:
        log.error(f"User {user_id}: Error generating summary via API: {e}", exc_info=True)
        return jsonify({"message": "Failed to generate summary."}), 500


@app.route('/api/trends/monthly_spending', methods=['GET'])
@login_required
def api_get_monthly_trends():
    # (Keep existing trends logic)
    # Similar to summary, insights.calculate_monthly_spending_trends might need context
    # for business-specific views (e.g., revenue trends vs. expense trends).
    user_id = current_user.id
    start_date_query = request.args.get('start_date')
    end_date_query = request.args.get('end_date')
    default_start_date = dt.date.today() - relativedelta(years=2)
    start_date = parse_date_param(start_date_query, default_start_date)
    end_date = parse_date_param(end_date_query, dt.date.today())
    if start_date_query and not start_date: return jsonify({"message": "Invalid start_date format."}), 400
    if end_date_query and not end_date: return jsonify({"message": "Invalid end_date format."}), 400
    if start_date and end_date and start_date > end_date: return jsonify({"message": "Start date > end date."}), 400
    start_param = start_date.isoformat() if start_date else None
    end_param = end_date.isoformat() if end_date else None
    log.info(f"User {user_id}: API calculating monthly trends. Start: {start_param}, End: {end_param}")
    try:
        transactions = database_supabase.get_all_transactions(user_id, start_param, end_param)
        if not transactions: return jsonify({})
        trends_data = insights.calculate_monthly_spending_trends(transactions=transactions)
        return jsonify(trends_data)
    except Exception as e:
        log.error(f"User {user_id}: Error calculating trends via API: {e}", exc_info=True)
        return jsonify({"message": "Failed to calculate trends."}), 500

@app.route('/api/recurring', methods=['GET'])
@login_required
def api_get_recurring():
    # (Keep existing recurring detection logic)
    user_id = current_user.id
    try:
        min_occurrences = int(request.args.get('min_occurrences', 3))
        days_tolerance = int(request.args.get('days_tolerance', 5))
        amount_tolerance_percent = float(request.args.get('amount_tolerance_percent', 10.0))
    except (ValueError, TypeError):
        return jsonify({"message": "Invalid query parameter type."}), 400
    log.info(f"User {user_id}: API detecting recurring txns: min={min_occurrences}, days={days_tolerance}, amt%={amount_tolerance_percent}")
    try:
        all_transactions = database_supabase.get_all_transactions(user_id=user_id)
        if not all_transactions: return jsonify([])
        recurring_data = insights.identify_recurring_transactions(
            all_transactions, min_occurrences, days_tolerance, amount_tolerance_percent
        )
        return jsonify(recurring_data)
    except Exception as e:
        log.error(f"User {user_id}: Error detecting recurring via API: {e}", exc_info=True)
        return jsonify({"message": "Failed to detect recurring transactions."}), 500

# --- LLM API Endpoints ---
@app.route('/api/ask', methods=['GET'])
@login_required
def api_ask_llm():
    # (Keep existing LLM Q&A logic)
    # llm_service.answer_financial_question might need updates to understand
    # business context, transaction_origin, or new fields like client_name.
    user_id = current_user.id
    question = request.args.get('query')
    if not question: return jsonify({"message": "Missing 'query' parameter"}), 400

    today = dt.date.today()
    default_end_date_context = today
    default_start_date_context = today - relativedelta(years=2)
    start_date_context_str = default_start_date_context.isoformat()
    end_date_context_str = default_end_date_context.isoformat()
    log.info(f"User {user_id}: API /ask. Query: '{question}'. Context: {start_date_context_str} to {end_date_context_str}")

    calc_start_date, calc_end_date, is_single_date_query = default_start_date_context, default_end_date_context, False
    parsed_dates = parse_dates_from_query(question)
    if isinstance(parsed_dates, dt.date):
        calc_start_date, calc_end_date, is_single_date_query = parsed_dates, parsed_dates, True
    elif isinstance(parsed_dates, tuple):
        calc_start_date, calc_end_date = parsed_dates
    calc_start_date_str, calc_end_date_str = (d.isoformat() if d else None for d in [calc_start_date, calc_end_date])

    pre_calculated_result: Optional[Decimal] = None
    # (Pre-calculation logic remains here - for brevity, not fully reproduced)
    # ...
    try:
        # Determine transactions for LLM context
        if is_single_date_query and calc_start_date_str:
            transactions_for_llm = database.get_all_transactions(user_id, calc_start_date_str, calc_start_date_str)
            summary_data_for_llm, context_start_str, context_end_str = None, calc_start_date_str, calc_start_date_str
        else:
            transactions_for_llm = database_supabase.get_all_transactions(user_id, start_date_context_str, end_date_context_str)
            summary_data_for_llm = insights.calculate_summary_insights(transactions_for_llm) if transactions_for_llm else None
            context_start_str, context_end_str = start_date_context_str, end_date_context_str

        llm_answer_text, llm_status = llm_service.answer_financial_question(
            question, transactions_for_llm, summary_data_for_llm,
            context_start_str, context_end_str, pre_calculated_result
        )
        if llm_status != 'success':
            reason = llm_status
            # (Log failed query logic remains here)
            # ...
            database_supabase.log_llm_failed_query(user_id, question, llm_answer_text, reason)
        return jsonify({"question": question, "answer": llm_answer_text})
    except Exception as e:
        log.error(f"User {user_id}: Error during LLM Q&A API: {e}", exc_info=True)
        return jsonify({"message": f"Failed to get answer from LLM: {type(e).__name__}"}), 500


# --- Feedback API Routes ---
@app.route('/api/report_error', methods=['POST'])
@login_required
def api_report_llm_error():
    # (Keep existing error reporting logic)
    user_id = current_user.id
    if not request.is_json: return jsonify({"message": "Request must be JSON"}), 400
    data = request.get_json()
    original_query, incorrect_response, user_comment = data.get('query'), data.get('incorrect_response'), data.get('user_comment')
    if not original_query or not incorrect_response: return jsonify({"message": "Missing 'query' or 'incorrect_response'"}), 400
    log.info(f"User {user_id} reporting LLM error for query: '{original_query}'")
    try:
        database_supabase.log_llm_user_report(user_id, original_query, incorrect_response, user_comment)
        return jsonify({"message": "Error report submitted."}), 201
    except Exception as e:
        log.error(f"User {user_id}: Failed to log LLM error report: {e}", exc_info=True)
        return jsonify({"message": "Failed to submit error report."}), 500

@app.route('/api/submit_feedback', methods=['POST'])
def api_submit_general_feedback():
    # (Keep existing general feedback logic)
    user_id = current_user.id if current_user.is_authenticated else None
    if not request.is_json: return jsonify({"message": "Request must be JSON"}), 400
    data = request.get_json()
    feedback_type, comment, contact_email = data.get('feedback_type'), data.get('comment'), data.get('contact_email')
    if not comment: return jsonify({"message": "Missing 'comment'"}), 400
    log.info(f"Received general feedback (User: {user_id if user_id else 'Anon'}). Type: {feedback_type}")
    try:
        database.log_user_feedback(user_id, feedback_type, comment, contact_email)
        return jsonify({"message": "Feedback submitted."}), 201
    except Exception as e:
        log.error(f"Failed to log user feedback (User: {user_id}): {e}", exc_info=True)
        return jsonify({"message": "Failed to submit feedback."}), 500

# --- Favicon Route ---
@app.route('/favicon.ico')
def favicon():
    # (Keep existing favicon logic)
    favicon_path = os.path.join(app.static_folder, 'favicon.ico')
    if os.path.exists(favicon_path):
        return send_from_directory(app.static_folder, 'favicon.ico', mimetype='image/vnd.microsoft.icon')
    flask_static_folder = os.path.join(app.root_path, 'static')
    flask_favicon_path = os.path.join(flask_static_folder, 'favicon.ico')
    if os.path.exists(flask_favicon_path):
        return send_from_directory(flask_static_folder, 'favicon.ico', mimetype='image/vnd.microsoft.icon')
    return '', 404

# --- Main Execution ---
if __name__ == '__main__':
    log.info(f"Starting SpendLens Flask server (Debug: {app.config.get('DEBUG', False)})...")
    app.run(host=app.config.get('HOST', '127.0.0.1'),
            port=app.config.get('PORT', 5001), # Ensure this matches your .env or config
            debug=app.config.get('DEBUG', False))

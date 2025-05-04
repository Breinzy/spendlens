import os
import logging
import re # Import regular expressions
import string # For punctuation removal
from flask import Flask, request, jsonify, render_template, redirect, url_for, send_from_directory, flash
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import datetime as dt
from dateutil.relativedelta import relativedelta
from dateutil.parser import parse as dateutil_parse, ParserError # For parsing flexible date strings
from decimal import Decimal, InvalidOperation
from typing import Optional, List, Dict, Any, Tuple, Union # Added Union

# --- Flask Extension Imports ---
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user

# Local imports
import database
import parser
import insights
import llm_service
from config import Config

# --- Flask App Setup ---
app = Flask(__name__) # Flask will look for templates in a 'templates' folder
app.config.from_object(Config)

# Configure logging
log = logging.getLogger('app')
log.setLevel(logging.INFO) # Set to DEBUG to see more detailed logs if needed
if not log.handlers:
    handler = logging.StreamHandler()
    # Include function name in formatter for better debugging
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s:%(funcName)s] - %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)

# --- Initialize Flask Extensions ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

# Ensure upload folder exists
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])
    log.info(f"Created upload folder: {app.config['UPLOAD_FOLDER']}")

# --- Database Initialization ---
try:
    database.initialize_database()
except Exception as e:
    log.critical(f"Failed to initialize database on startup: {e}", exc_info=True)
    # exit(1)

# --- User Loader for Flask-Login ---
@login_manager.user_loader
def load_user(user_id):
    try:
        return database.find_user_by_id(int(user_id))
    except ValueError: return None
    except Exception as e:
        log.error(f"Error loading user {user_id}: {e}", exc_info=True)
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

# --- UPDATED HELPER: Parse Dates/Ranges from Query ---
def parse_dates_from_query(query: str) -> Optional[Union[Tuple[dt.date, dt.date], dt.date]]:
    """
    Attempts to parse a date range OR a single specific date from a query string.
    Returns:
        - Tuple (start_date, end_date) if a range is found.
        - dt.date object if a single specific date is found.
        - None if no clear date/range is found.
    """
    q_lower = query.lower()
    today = dt.date.today()
    current_year = today.year
    month_pattern = r'\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b'

    # --- Try parsing specific single dates first ---
    try:
        specific_date_match = re.search(r'\b(?:on\s+|date\s+)?(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|' + month_pattern + r'\s+\d{1,2}(?:st|nd|rd|th)?(?:,\s*\d{4})?)\b', q_lower)
        if specific_date_match:
             date_str_to_parse = specific_date_match.group(1) # The actual date part captured
             log.debug(f"Potential single date string found: '{date_str_to_parse}'")
             is_likely_just_month = re.fullmatch(month_pattern, date_str_to_parse.strip())
             if not is_likely_just_month:
                 parsed_dt = dateutil_parse(date_str_to_parse, fuzzy=False)
                 specific_date = parsed_dt.date()
                 if parsed_dt.year >= 1990 and (parsed_dt.year != current_year or str(current_year) in date_str_to_parse or re.search(r'\b\d{1,2}(?:st|nd|rd|th)\b', date_str_to_parse)):
                     log.info(f"Parsed specific single date from query: {specific_date}")
                     return specific_date
                 else: log.debug("Parsed date seemed ambiguous (likely just month/day), continuing...")
    except (ParserError, ValueError, OverflowError, TypeError, AttributeError) as e:
         log.debug(f"Dateutil parsing for single date failed or was ambiguous: {e}")
         pass

    # --- If no single date, check for Ranges ---

    # Check for "month this year"
    month_this_year_match = re.search(f'({month_pattern})\\s+this\\s+year', q_lower)
    if month_this_year_match:
        month_str = month_this_year_match.group(1)
        try:
            month_dt = dateutil_parse(f"{month_str} 1, {current_year}"); month = month_dt.month
            start_date = dt.date(current_year, month, 1)
            end_date = (start_date + relativedelta(months=1)) - dt.timedelta(days=1)
            log.info(f"Parsed 'month this year' range from query: {start_date} to {end_date}")
            return start_date, end_date
        except (ValueError, OverflowError) as e: log.warning(f"Could not parse month for 'month this year': '{month_str} this year': {e}")

    # Check for "month year" (with digits)
    month_year_match = re.search(f'({month_pattern})\\s+(\\d{{4}})', q_lower)
    if month_year_match:
        month_str, year_str = month_year_match.groups(); year = int(year_str)
        try:
            month_dt = dateutil_parse(f"{month_str} 1, {year}"); month = month_dt.month
            start_date = dt.date(year, month, 1)
            end_date = (start_date + relativedelta(months=1)) - dt.timedelta(days=1)
            log.info(f"Parsed 'month year' range from query: {start_date} to {end_date}")
            return start_date, end_date
        except (ValueError, OverflowError) as e: log.warning(f"Could not parse month/year '{month_str} {year_str}': {e}")

    # --- UPDATED: Check for standalone month name (assume current year) ---
    # Look for month name not followed immediately by 'this year' or digits
    standalone_month_match = re.search(f'({month_pattern})(?!\\s*(?:this\\s+year|\\d))', q_lower)
    if standalone_month_match:
         month_str = standalone_month_match.group(1)
         # Check if it was already matched as part of month-year above
         if not (month_year_match and month_year_match.group(1) == month_str) and \
            not (month_this_year_match and month_this_year_match.group(1) == month_str):
             try:
                month_dt = dateutil_parse(f"{month_str} 1, {current_year}") # Use current year
                month = month_dt.month
                start_date = dt.date(current_year, month, 1)
                end_date = (start_date + relativedelta(months=1)) - dt.timedelta(days=1)
                log.info(f"Parsed standalone month '{month_str}' (assuming current year) range from query: {start_date} to {end_date}")
                return start_date, end_date
             except (ValueError, OverflowError) as e:
                log.warning(f"Could not parse standalone month '{month_str}': {e}")
    # --- END UPDATE ---

    # Check for "last month"
    if "last month" in q_lower:
        end_of_last_month = today.replace(day=1) - dt.timedelta(days=1)
        start_of_last_month = end_of_last_month.replace(day=1)
        log.info(f"Parsed 'last month' range from query: {start_of_last_month} to {end_of_last_month}")
        return start_of_last_month, end_of_last_month

    # Check for "this month"
    if "this month" in q_lower:
        start_of_this_month = today.replace(day=1)
        end_of_this_month = today
        log.info(f"Parsed 'this month' range from query: {start_of_this_month} to {end_of_this_month}")
        return start_of_this_month, end_of_this_month

    # Check for "year" (ensure it doesn't overlap with month checks)
    if not month_year_match and not month_this_year_match and not standalone_month_match:
        year_match = re.search(r'\b(in|for|during)\s+(\d{4})\b|\b(\d{4})\b', q_lower)
        if year_match:
            year_str = year_match.group(2) or year_match.group(3)
            year = int(year_str)
            if 1990 < year <= current_year + 1:
                start_date = dt.date(year, 1, 1); end_date = dt.date(year, 12, 31)
                log.info(f"Parsed 'year' range from query: {start_date} to {end_date}")
                return start_date, end_date

    # Check for "this year" (only if more specific patterns didn't match)
    if "this year" in q_lower and not month_this_year_match and not standalone_month_match:
        start_date = dt.date(current_year, 1, 1); end_date = dt.date(current_year, 12, 31)
        log.info(f"Parsed 'this year' range from query: {start_date} to {end_date}")
        return start_date, end_date

    # Check for "last year"
    if "last year" in q_lower:
        year = current_year - 1; start_date = dt.date(year, 1, 1); end_date = dt.date(year, 12, 31)
        log.info(f"Parsed 'last year' range from query: {start_date} to {end_date}")
        return start_date, end_date

    log.debug(f"No specific date or range parsed from query: '{query}'")
    return None

# --- Routes ---
# ... (index, register, login, logout routes remain the same) ...
@app.route('/')
def index():
    if current_user.is_authenticated: return f"Welcome {current_user.username}! Use API endpoints or dashboard (TBD)."
    else: return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    # ... registration logic ...
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username'); password = request.form.get('password'); confirm_password = request.form.get('confirm_password')
        if not username or not password or not confirm_password: flash('All fields are required.', 'warning'); return redirect(url_for('register'))
        if password != confirm_password: flash('Passwords do not match.', 'danger'); return redirect(url_for('register'))
        if database.find_user_by_username(username): flash('Username already exists.', 'warning'); return redirect(url_for('register'))
        hashed_password = generate_password_hash(password)
        user_id = database.create_user(username, hashed_password)
        if user_id: log.info(f"User '{username}' registered."); flash(f'Account created! Please log in.', 'success'); return redirect(url_for('login'))
        else: log.error(f"Failed to create user '{username}'."); flash('Account creation failed.', 'danger'); return redirect(url_for('register'))
    return render_template('register.html', title='Register')

@app.route('/login', methods=['GET', 'POST'])
def login():
    # ... login logic ...
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username'); password = request.form.get('password'); remember = bool(request.form.get('remember'))
        if not username or not password: flash('Username and password are required.', 'warning'); return redirect(url_for('login'))
        user = database.find_user_by_username(username)
        if user and check_password_hash(user.password_hash, password):
            login_user(user, remember=remember); log.info(f"User '{username}' logged in."); next_page = request.args.get('next')
            if next_page and not next_page.startswith('/'): next_page = url_for('index') # Prevent open redirect
            return redirect(next_page or url_for('index'))
        else: log.warning(f"Failed login for: {username}"); flash('Login unsuccessful.', 'danger'); return redirect(url_for('login'))
    return render_template('login.html', title='Login')

@app.route('/logout')
@login_required
def logout():
    # ... logout logic ...
    log.info(f"User '{current_user.username}' logging out."); logout_user(); flash('Logged out.', 'info'); return redirect(url_for('login'))


# --- Protected Data Routes (Require Login) ---

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_file_protected():
    # ... (upload logic remains the same, using current_user.id) ...
    user_id = current_user.id; log.info(f"Upload request from user {user_id}")
    if request.method == 'POST':
        if 'checking_file' not in request.files and 'credit_file' not in request.files: return jsonify({"error": "No file part"}), 400
        files_processed, all_transactions, errors = [], [], []
        try: database.clear_transactions_for_user(user_id); database.clear_llm_rules_for_user(user_id); log.info(f"Cleared data for user {user_id}.")
        except Exception as e: log.error(f"Error clearing data for user {user_id}: {e}", exc_info=True); return jsonify({"error": "Failed prep."}), 500
        checking_file = request.files.get('checking_file')
        if checking_file and checking_file.filename and allowed_file(checking_file.filename):
             filename = secure_filename(checking_file.filename); filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
             try:
                 checking_file.save(filepath); log.info(f"User {user_id}: Saved {filename}")
                 txns = parser.parse_checking_csv(user_id, filepath); all_transactions.extend(txns); files_processed.append(filename); log.info(f"User {user_id}: Parsed {len(txns)} txns.")
             except Exception as e: log.error(f"User {user_id}: Error processing {filename}: {e}", exc_info=True); errors.append(f"Error: {filename}: {e}")
             finally:
                  if os.path.exists(filepath):
                      try: os.remove(filepath); log.info(f"Removed uploaded file: {filepath}")
                      except OSError as e: log.error(f"Error removing uploaded file {filepath}: {e}")
        credit_file = request.files.get('credit_file')
        if credit_file and credit_file.filename and allowed_file(credit_file.filename):
             filename = secure_filename(credit_file.filename); filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
             try:
                 credit_file.save(filepath); log.info(f"User {user_id}: Saved {filename}")
                 txns = parser.parse_credit_csv(user_id, filepath); all_transactions.extend(txns); files_processed.append(filename); log.info(f"User {user_id}: Parsed {len(txns)} txns.")
             except Exception as e: log.error(f"User {user_id}: Error processing {filename}: {e}", exc_info=True); errors.append(f"Error: {filename}: {e}")
             finally:
                  if os.path.exists(filepath):
                      try: os.remove(filepath); log.info(f"Removed uploaded file: {filepath}")
                      except OSError as e: log.error(f"Error removing uploaded file {filepath}: {e}")
        saved_count = 0
        if all_transactions:
             try: database.save_transactions(user_id, all_transactions); saved_count = len(all_transactions)
             except Exception as e: log.error(f"User {user_id}: Error saving txns: {e}", exc_info=True); errors.append(f"DB save error.")
        llm_suggestions_count = 0
        if saved_count > 0 and not errors:
             try:
                 log.info(f"User {user_id}: Starting LLM suggestion..."); uncategorized_tx = [tx for tx in all_transactions if tx.category == 'Uncategorized']; log.info(f"User {user_id}: Found {len(uncategorized_tx)} uncategorized.")
                 if uncategorized_tx:
                      valid_categories = ["Food", "Groceries", "Restaurants", "Coffee Shops", "Shopping", "Clothing", "Electronics", "Home Goods", "Utilities", "Electricity", "Gas", "Water", "Internet", "Phone", "Rent", "Mortgage", "Housing", "Transportation", "Gas", "Public Transport", "Car Maintenance", "Parking", "Health & Wellness", "Gym", "Pharmacy", "Doctor", "Entertainment", "Movies", "Games", "Subscriptions", "Books", "Travel", "Flights", "Hotels", "Vacation", "Income", "Salary", "Freelance", "Other Income", "Taxes", "Transfers", "Payments", "Investment", "Savings", "Personal Care", "Gifts", "Charity", "Education", "Business Expense", "Miscellaneous", "Ignore", "Uncategorized"]
                      context_rules = {}; context_rules.update(parser.VENDOR_RULES); user_specific_rules = database.get_user_rules(user_id); context_rules.update(user_specific_rules)
                      suggested_rules_map = llm_service.suggest_categories_for_transactions(uncategorized_tx, valid_categories, context_rules)
                      if suggested_rules_map:
                           log.info(f"User {user_id}: Received {len(suggested_rules_map)} suggestions. Saving...");
                           for desc_key, suggested_cat in suggested_rules_map.items(): parser.save_llm_rule(user_id, desc_key, suggested_cat); llm_suggestions_count += 1
                           log.info(f"User {user_id}: Saved {llm_suggestions_count} LLM rules.")
                      else: log.info(f"User {user_id}: LLM provided no suggestions.")
                 else: log.info(f"User {user_id}: No 'Uncategorized' txns for LLM.")
             except Exception as llm_error: log.error(f"User {user_id}: LLM suggestion error: {llm_error}", exc_info=True); errors.append(f"LLM Suggestion Error.")
        final_message = f"Processed {saved_count} txns from {len(files_processed)} files.";
        if llm_suggestions_count > 0: final_message += f" Saved {llm_suggestions_count} AI suggestions."
        if not files_processed and not errors: return jsonify({"error": "No valid files uploaded."}), 400
        elif errors: return jsonify({"message": final_message + " Encountered errors.", "files": files_processed, "errors": errors}), 500
        else: return jsonify({"message": final_message, "files": files_processed}), 201
    return render_template('upload.html')

@app.route('/transactions', methods=['GET'])
@login_required
def get_transactions_protected():
    # ... (logic remains the same, using current_user.id) ...
    user_id = current_user.id; start_date_str = request.args.get('start_date'); end_date_str = request.args.get('end_date'); category = request.args.get('category')
    log.info(f"User {user_id}: /transactions request: start={start_date_str}, end={end_date_str}, category={category}")
    start_date_obj, end_date_obj = None, None
    try:
        if start_date_str: start_date_obj = dt.datetime.strptime(start_date_str, '%Y-%m-%d').date()
        if end_date_str: end_date_obj = dt.datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except ValueError: return jsonify({"error": "Invalid date format."}), 400
    if start_date_obj and end_date_obj and start_date_obj > end_date_obj: return jsonify({"error": "start_date > end_date."}), 400
    try:
        transactions = database.get_all_transactions(user_id, start_date_str, end_date_str, category)
        transactions_dict = [tx.to_dict() for tx in transactions]; log.info(f"User {user_id}: Returning {len(transactions_dict)} txns."); return jsonify(transactions_dict)
    except Exception as e: log.error(f"User {user_id}: Error getting txns: {e}", exc_info=True); return jsonify({"error": "Failed get."}), 500

@app.route('/transactions/<int:transaction_id>/category', methods=['PUT'])
@login_required
def update_category_protected(transaction_id):
    # ... (logic remains the same, using current_user.id) ...
    user_id = current_user.id
    if not request.is_json: return jsonify({"error": "Request must be JSON"}), 400
    data = request.get_json(); new_category = data.get('category')
    if not new_category or not isinstance(new_category, str): return jsonify({"error": "Missing/invalid 'category'"}), 400
    log.info(f"User {user_id}: Update category for Tx {transaction_id} to '{new_category}'")
    try:
        transactions = database.get_all_transactions(user_id=user_id); tx_to_update = next((tx for tx in transactions if tx.id == transaction_id), None)
        if not tx_to_update: return jsonify({"error": "Transaction not found"}), 404
        success = database.update_transaction_category(user_id, transaction_id, new_category)
        if success:
            desc_for_rule = tx_to_update.raw_description or tx_to_update.description
            if desc_for_rule: parser.add_user_rule(user_id, desc_for_rule, new_category); log.info(f"User {user_id}: Saved user rule.")
            else: log.warning(f"User {user_id}: Tx {transaction_id} has no description for rule.")
            return jsonify({"message": f"Tx {transaction_id} updated to '{new_category}'"}), 200
        else: return jsonify({"error": "Failed to update category"}), 500
    except Exception as e: log.error(f"User {user_id}: Error updating category {transaction_id}: {e}", exc_info=True); return jsonify({"error": "Unexpected error."}), 500


# --- Analysis Endpoints (Protected) ---

@app.route('/summary', methods=['GET'])
@login_required
def get_summary_protected():
    # ... (logic remains the same, using current_user.id) ...
    user_id = current_user.id; today = dt.date.today(); default_end_date = today; default_start_date = today - relativedelta(years=2)
    start_date_query = request.args.get('start_date'); end_date_query = request.args.get('end_date')
    start_date = parse_date_param(start_date_query, default_start_date); end_date = parse_date_param(end_date_query, default_end_date)
    if start_date and end_date and start_date > end_date: return jsonify({"error": "start_date > end_date."}), 400
    start_date_str = start_date.isoformat() if start_date else None; end_date_str = end_date.isoformat() if end_date else None
    log.info(f"User {user_id}: Generating summary: {start_date_str} to {end_date_str}")
    try:
        transactions_for_period = database.get_all_transactions(user_id, start_date_str, end_date_str)
        summary_data = insights.calculate_summary_insights(transactions_for_period); return jsonify(summary_data)
    except AttributeError as e:
        if 'calculate_summary_insights' in str(e): log.error(f"AttributeError: 'calculate_summary_insights' not found.", exc_info=True); return jsonify({"error": "Internal server error: Summary function missing."}), 500
        else: log.error(f"User {user_id}: AttributeError generating summary: {e}", exc_info=True); return jsonify({"error": "Internal server error."}), 500
    except Exception as e: log.error(f"User {user_id}: Error generating summary: {e}", exc_info=True); return jsonify({"error": "Failed to generate summary."}), 500

@app.route('/trends/monthly_spending', methods=['GET'])
@login_required
def get_monthly_trends_protected():
    # ... (logic remains the same, using current_user.id) ...
    user_id = current_user.id; start_date_query = request.args.get('start_date'); end_date_query = request.args.get('end_date')
    start_date, end_date = None, None
    if start_date_query: start_date = parse_date_param(start_date_query, None);
    if not start_date and start_date_query: return jsonify({"error": "Invalid start_date."}), 400
    if end_date_query: end_date = parse_date_param(end_date_query, None);
    if not end_date and end_date_query: return jsonify({"error": "Invalid end_date."}), 400
    if start_date and end_date and start_date > end_date: return jsonify({"error": "start_date > end_date."}), 400
    log.info(f"User {user_id}: Calculating monthly trends. Start: {start_date}, End: {end_date}")
    try:
        transactions = database.get_all_transactions(user_id, start_date.isoformat() if start_date else None, end_date.isoformat() if end_date else None)
        trends_data = insights.calculate_monthly_spending_trends(transactions=transactions); return jsonify(trends_data)
    except Exception as e: log.error(f"User {user_id}: Error calculating trends: {e}", exc_info=True); return jsonify({"error": "Failed to calculate trends."}), 500

@app.route('/recurring', methods=['GET'])
@login_required
def get_recurring_protected():
    # ... (logic remains the same, using current_user.id) ...
    user_id = current_user.id
    try: min_occurrences = int(request.args.get('min_occurrences', 3)); days_tolerance = int(request.args.get('days_tolerance', 5)); amount_tolerance_percent = float(request.args.get('amount_tolerance_percent', 10.0))
    except (ValueError, TypeError): return jsonify({"error": "Invalid query parameter type."}), 400
    log.info(f"User {user_id}: Detecting recurring txns: min={min_occurrences}, days={days_tolerance}, amount%={amount_tolerance_percent}")
    try:
        all_transactions = database.get_all_transactions(user_id=user_id)
        recurring_data = insights.identify_recurring_transactions(all_transactions, min_occurrences, days_tolerance, amount_tolerance_percent); return jsonify(recurring_data)
    except AttributeError as e:
         if 'identify_recurring_transactions' in str(e): log.error(f"AttributeError: 'identify_recurring_transactions' not found.", exc_info=True); return jsonify({"error": "Internal server error: Recurring function missing."}), 500
         else: log.error(f"User {user_id}: AttributeError detecting recurring: {e}", exc_info=True); return jsonify({"error": "Internal server error."}), 500
    except Exception as e: log.error(f"User {user_id}: Error detecting recurring: {e}", exc_info=True); return jsonify({"error": "Failed to detect recurring."}), 500

# --- LLM Endpoints (Protected) ---

@app.route('/analysis/llm_summary', methods=['GET'])
@login_required
def get_llm_summary_protected():
    # ... (logic remains the same, using current_user.id) ...
    user_id = current_user.id; today = dt.date.today(); default_end_date = today.replace(day=1) - dt.timedelta(days=1); default_start_date = (default_end_date.replace(day=1) - relativedelta(months=2))
    start_date_query = request.args.get('start_date'); end_date_query = request.args.get('end_date')
    start_date = parse_date_param(start_date_query, default_start_date); end_date = parse_date_param(end_date_query, default_end_date)
    if start_date and end_date and start_date > end_date: return jsonify({"error": "start_date > end_date."}), 400
    start_date_str = start_date.isoformat() if start_date else None; end_date_str = end_date.isoformat() if end_date else None
    log.info(f"User {user_id}: Generating LLM summary: {start_date_str} to {end_date_str}")
    try:
        transactions_for_period = database.get_all_transactions(user_id, start_date_str, end_date_str)
        summary_data = insights.calculate_summary_insights(transactions_for_period)
        trends_data = insights.calculate_monthly_spending_trends(transactions=transactions_for_period)
        llm_summary_text = llm_service.generate_financial_summary(summary_data, trends_data, start_date_str, end_date_str); return jsonify({"summary": llm_summary_text})
    except AttributeError as e: log.error(f"User {user_id}: AttributeError generating LLM summary: {e}", exc_info=True); return jsonify({"error": "Internal server error: Analysis function missing."}), 500
    except Exception as e: log.error(f"User {user_id}: Error generating LLM summary: {e}", exc_info=True); return jsonify({"error": f"Failed to generate LLM summary: {type(e).__name__}"}), 500


@app.route('/ask', methods=['GET'])
@login_required # Protect this route
def ask_llm_protected():
    """Answers a financial question using the LLM for the logged-in user."""
    user_id = current_user.id
    question = request.args.get('query')
    if not question:
        return jsonify({"error": "Missing 'query' parameter"}), 400

    # --- Default Date Range for LLM Context ---
    today = dt.date.today()
    default_end_date_context = today
    default_start_date_context = today - relativedelta(years=2)
    start_date_context_str = default_start_date_context.isoformat()
    end_date_context_str = default_end_date_context.isoformat()
    log.info(f"User {user_id}: Received /ask request. Query: '{question}'. Default context range: {start_date_context_str} to {end_date_context_str}")

    # --- Date Parsing from Query for Pre-calculation AND Specific Filtering ---
    calc_start_date = None
    calc_end_date = None
    is_single_date_query = False
    parsed_dates = parse_dates_from_query(question) # Returns Tuple[date, date] or date or None

    if isinstance(parsed_dates, dt.date): # Specific single date found
        calc_start_date = parsed_dates
        calc_end_date = parsed_dates
        is_single_date_query = True
        log.info(f"User {user_id}: Parsed specific single date from query: {calc_start_date}")
    elif isinstance(parsed_dates, tuple): # Specific date range found
        calc_start_date, calc_end_date = parsed_dates
        log.info(f"User {user_id}: Parsed specific date range from query: {calc_start_date} to {calc_end_date}")
    else: # No specific date/range found in query
        calc_start_date = default_start_date_context
        calc_end_date = default_end_date_context
        log.info(f"User {user_id}: No specific date/range in query, using default range for potential calculation: {calc_start_date} to {calc_end_date}")

    calc_start_date_str = calc_start_date.isoformat() if calc_start_date else None
    calc_end_date_str = calc_end_date.isoformat() if calc_end_date else None

    # --- Pre-calculation Logic ---
    pre_calculated_result: Optional[Decimal] = None
    calculation_performed = False
    q_lower = question.lower()
    try:
        income_keywords = ("income", "earn", "deposit", "payroll")
        spending_keywords = ("spending", "spent", "cost", "pay for", "expense", "spend") # Added spend
        calc_keywords = ("total", "how much", "sum", "what is", "what was") # Added 'what is/was'

        is_income_q = any(kw in q_lower for kw in income_keywords)
        is_spending_q = any(kw in q_lower for kw in spending_keywords)
        is_calc_q = any(kw in q_lower for kw in calc_keywords)

        log.debug(f"Pre-calc check: is_calc_q={is_calc_q}, is_single_date_query={is_single_date_query}, date_range_valid={bool(calc_start_date_str and calc_end_date_str)}")

        # Perform calculation ONLY if it's a calculation question AND we have a valid date range
        # AND it's not a single date query (pre-calc doesn't make sense for single dates)
        if is_calc_q and not is_single_date_query and calc_start_date_str and calc_end_date_str:
            log.debug(f"User {user_id}: Checking calculation type: is_income_q={is_income_q}, is_spending_q={is_spending_q}")
            if is_income_q:
                log.info(f"User {user_id}: Detected potential income calculation request for range {calc_start_date_str} to {calc_end_date_str}.")
                pre_calculated_result = database.calculate_total_for_period(user_id, calc_start_date_str, calc_end_date_str, transaction_type='income', exclude_categories=['Payments', 'Transfers'])
                calculation_performed = True; log.info(f"User {user_id}: Pre-calculated income result: {pre_calculated_result}")

            elif is_spending_q:
                log.info(f"User {user_id}: Detected potential spending calculation request for range {calc_start_date_str} to {calc_end_date_str}.")
                category_to_calc = None; words = q_lower.split()
                extracted_category_word = None
                # --- UPDATED Category Extraction ---
                if " on " in q_lower:
                    try:
                        match = re.search(r'\bspend(?:ing|t)?\s+on\s+([\w\s]+?)(?:\s+in|\s+for|\s+during|\s+last|\s+this|\?|$)', q_lower)
                        if match: extracted_category_word = match.group(1).strip()
                        log.debug(f"Regex match for 'on': {match.groups() if match else 'None'}")
                    except Exception as e: log.warning(f"Regex error for 'on': {e}")
                elif " for " in q_lower:
                     try:
                        match = re.search(r'\b(?:spending|spent|cost)\s+for\s+([\w\s]+?)(?:\s+in|\s+for|\s+during|\s+last|\s+this|\?|$)', q_lower)
                        if match: extracted_category_word = match.group(1).strip()
                        log.debug(f"Regex match for 'for': {match.groups() if match else 'None'}")
                     except Exception as e: log.warning(f"Regex error for 'for': {e}")

                if extracted_category_word:
                    translator = str.maketrans('', '', string.punctuation)
                    cleaned_word = extracted_category_word.translate(translator)
                    category_to_calc = cleaned_word.strip().capitalize()
                    log.info(f"Extracted category: {category_to_calc}") # Log extracted category
                else:
                     log.info("No category keyword ('on' or 'for') or pattern found for spending calculation.")
                # --- END Category Extraction ---

                log.debug(f"Calling calculate_total_for_period with: user_id={user_id}, start={calc_start_date_str}, end={calc_end_date_str}, category={category_to_calc}, type=spending")
                pre_calculated_result = database.calculate_total_for_period(user_id, calc_start_date_str, calc_end_date_str, category=category_to_calc, transaction_type='spending')
                calculation_performed = True; log.info(f"User {user_id}: Pre-calculated spending result: {pre_calculated_result}")
            else: # Added else for debugging
                 log.debug(f"User {user_id}: Not identified as income or spending calculation despite is_calc_q being True.")
        else:
            log.info(f"User {user_id}: Skipping pre-calculation (is_calc_q={is_calc_q}, is_single_date_query={is_single_date_query}, date_range_valid={bool(calc_start_date_str and calc_end_date_str)}).")

    except Exception as calc_error:
        log.error(f"User {user_id}: Error during pre-calculation attempt: {calc_error}", exc_info=True)
        calculation_performed = False; pre_calculated_result = None
    # --- End Pre-calculation Logic ---

    try:
        # --- Determine which transactions to send to LLM ---
        if is_single_date_query and calc_start_date_str:
            log.info(f"User {user_id}: Fetching transactions only for specific date {calc_start_date_str} for LLM context.")
            transactions_for_llm = database.get_all_transactions(user_id=user_id, start_date=calc_start_date_str, end_date=calc_start_date_str)
            summary_data_for_llm = None
            context_start_str = calc_start_date_str; context_end_str = calc_start_date_str
        else:
            log.info(f"User {user_id}: Fetching default context transaction window ({start_date_context_str} to {end_date_context_str}) for LLM.")
            transactions_for_llm = database.get_all_transactions(user_id=user_id, start_date=start_date_context_str, end_date=end_date_context_str)
            summary_data_for_llm = insights.calculate_summary_insights(transactions_for_llm)
            context_start_str = start_date_context_str; context_end_str = end_date_context_str
        # --- End Transaction Fetch Logic ---


        # --- Call LLM service and handle status ---
        llm_answer_text, llm_status = llm_service.answer_financial_question(
            question=question,
            transactions=transactions_for_llm,
            summary_data=summary_data_for_llm,
            start_date_str=context_start_str,
            end_date_str=context_end_str,
            pre_calculated_result=pre_calculated_result
        )

        # --- Log failed queries based on status ---
        if llm_status == 'cannot_answer' or llm_status == 'blocked' or llm_status == 'error':
             log.warning(f"LLM Q&A for user {user_id} failed with status '{llm_status}'. Logging failure.")
             reason = llm_status
             if llm_status == 'blocked' and 'Reason:' in llm_answer_text:
                  try: reason = f"blocked: {llm_answer_text.split('Reason:')[1].split(')')[0].strip()}"
                  except: pass
             elif llm_status == 'error' and 'Error:' in llm_answer_text:
                   try: reason = f"error: {llm_answer_text.split('Error:')[1].strip()}"
                   except: pass

             database.log_llm_failed_query(
                 user_id=user_id,
                 query=question,
                 llm_response=llm_answer_text,
                 reason=reason
             )
        # --- End logging failed queries ---

        log.info(f"User {user_id}: LLM answer generated with status: {llm_status}.")
        return jsonify({"question": question, "answer": llm_answer_text}) # Return only the answer text

    except AttributeError as attr_err:
        if 'calculate_summary_insights' in str(attr_err): log.error(f"User {user_id}: AttributeError - 'calculate_summary_insights' not found.", exc_info=True); return jsonify({"error": "Internal server error: Summary function missing."}), 500
        else: log.error(f"User {user_id}: AttributeError during LLM Q&A: {attr_err}", exc_info=True); return jsonify({"error": f"Failed to get answer from LLM: AttributeError"}), 500
    except Exception as e: log.error(f"User {user_id}: Error during LLM Q&A: {e}", exc_info=True); return jsonify({"error": f"Failed to get answer from LLM: {type(e).__name__}"}), 500


# --- NEW FEEDBACK ROUTES ---

@app.route('/report_error', methods=['POST'])
@login_required
def report_llm_error():
    """Allows logged-in users to report incorrect LLM answers."""
    user_id = current_user.id
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    original_query = data.get('query')
    incorrect_response = data.get('incorrect_response')
    user_comment = data.get('user_comment') # Optional

    if not original_query or not incorrect_response:
        return jsonify({"error": "Missing 'query' or 'incorrect_response' in request body"}), 400

    log.info(f"User {user_id} reporting LLM error for query: '{original_query}'")
    try:
        database.log_llm_user_report(user_id, original_query, incorrect_response, user_comment)
        return jsonify({"message": "Error report submitted successfully."}), 201
    except Exception as e:
        log.error(f"User {user_id}: Failed to log LLM error report: {e}", exc_info=True)
        return jsonify({"error": "Failed to submit error report."}), 500


@app.route('/submit_feedback', methods=['POST'])
# Allow anonymous feedback, but capture user if logged in
def submit_general_feedback():
    """Allows users (logged in or anonymous) to submit general feedback."""
    user_id = current_user.id if current_user.is_authenticated else None

    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    feedback_type = data.get('feedback_type') # e.g., bug, suggestion, general
    comment = data.get('comment')
    contact_email = data.get('contact_email') # Optional

    if not comment:
        return jsonify({"error": "Missing 'comment' in request body"}), 400
    if feedback_type and not isinstance(feedback_type, str):
         return jsonify({"error": "Invalid 'feedback_type'"}), 400
    if contact_email and not isinstance(contact_email, str): # Basic validation
         return jsonify({"error": "Invalid 'contact_email'"}), 400


    log.info(f"Received general feedback (User: {user_id if user_id else 'Anonymous'}). Type: {feedback_type}")
    try:
        database.log_user_feedback(user_id, feedback_type, comment, contact_email)
        return jsonify({"message": "Feedback submitted successfully."}), 201
    except Exception as e:
        log.error(f"Failed to log user feedback (User: {user_id}): {e}", exc_info=True)
        return jsonify({"error": "Failed to submit feedback."}), 500

# --- END FEEDBACK ROUTES ---


# --- Favicon Route (Optional) ---
@app.route('/favicon.ico')
def favicon():
    static_folder = os.path.join(app.root_path, 'static')
    favicon_path = os.path.join(static_folder, 'favicon.ico')
    if os.path.exists(favicon_path):
        return send_from_directory(static_folder, 'favicon.ico', mimetype='image/vnd.microsoft.icon')
    else:
        return '', 404

# --- Main Execution ---
if __name__ == '__main__':
    database.initialize_database()
    app.run(host=app.config.get('HOST', '127.0.0.1'),
            port=app.config.get('PORT', 5001),
            debug=app.config.get('DEBUG', True))

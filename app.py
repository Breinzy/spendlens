import os
import logging
from flask import Flask, request, jsonify, render_template, redirect, url_for, send_from_directory
from werkzeug.utils import secure_filename
import datetime as dt
from dateutil.relativedelta import relativedelta
from decimal import Decimal, InvalidOperation
from typing import Optional, List, Dict, Any # <--- Added import for Optional and other types

# Local imports (assuming they are in the same directory or accessible via PYTHONPATH)
import database
import parser
import insights
import llm_service # Assuming llm_service.py exists
from config import Config # Assuming config.py exists

# --- Flask App Setup ---
app = Flask(__name__)
app.config.from_object(Config) # Load config from config.py

# Configure logging to match other modules
log = logging.getLogger('app') # Use specific logger name
log.setLevel(logging.INFO)
if not log.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)

# Ensure upload folder exists
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])
    log.info(f"Created upload folder: {app.config['UPLOAD_FOLDER']}")

# --- Database Initialization ---
# Ensure the database and table exist when the app starts
try:
    database.initialize_database()
except Exception as e:
    log.critical(f"Failed to initialize database on startup: {e}", exc_info=True)
    # Depending on the desired behavior, you might exit or continue with limited functionality
    # exit(1) # Uncomment to exit if DB initialization fails

# --- Helper Functions ---
def allowed_file(filename: str) -> bool:
    """Checks if the uploaded file has an allowed extension."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# --- CORRECTED FUNCTION SIGNATURE ---
def parse_date_param(date_str: Optional[str], default: Optional[dt.date]) -> Optional[dt.date]:
# --- END CORRECTION ---
    """Parses a date string (YYYY-MM-DD) or returns a default."""
    if not date_str:
        return default
    try:
        return dt.datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        log.warning(f"Invalid date format received: '{date_str}'. Using default: {default}")
        return default

# --- Routes ---

@app.route('/')
def index():
    """Serves the main HTML page."""
    # Redirect to upload page or a dashboard page if desired
    # For now, just indicate the backend is running
    return "SpendLens Backend is running. Use API endpoints."
    # If you create an index.html in a 'templates' folder:
    # return render_template('index.html')

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    """Handles file uploads via GET (shows form) and POST (processes files)."""
    if request.method == 'POST':
        if 'checking_file' not in request.files and 'credit_file' not in request.files:
            return jsonify({"error": "No file part in the request"}), 400

        files_processed = []
        all_transactions = []
        errors = []

        # --- Clear existing data before processing new files ---
        try:
            database.clear_transactions()
            parser.clear_user_rules() # Clears only memory, keeps user_rules.json
            log.info("Cleared existing transactions and user rules (memory only) before new upload.")
        except Exception as e:
            log.error(f"Error clearing database or user rules before upload: {e}", exc_info=True)
            return jsonify({"error": "Failed to prepare database for new upload."}), 500
        # --- End Clear Data ---

        # Process checking file
        checking_file = request.files.get('checking_file')
        if checking_file and checking_file.filename and allowed_file(checking_file.filename):
            filename = secure_filename(checking_file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            try:
                checking_file.save(filepath)
                log.info(f"Saved checking file: {filename}")
                # Determine account type based on filename or content if needed
                checking_transactions = parser.parse_checking_csv(filepath)
                all_transactions.extend(checking_transactions)
                files_processed.append(filename)
                log.info(f"Parsed {len(checking_transactions)} transactions from {filename}")
            except Exception as e:
                log.error(f"Error processing checking file {filename}: {e}", exc_info=True)
                errors.append(f"Error processing {filename}: {e}")
            finally:
                 # Clean up uploaded file after processing
                 if os.path.exists(filepath):
                     try: os.remove(filepath); log.info(f"Removed uploaded file: {filepath}")
                     except OSError as e: log.error(f"Error removing uploaded file {filepath}: {e}")

        # Process credit card file
        credit_file = request.files.get('credit_file')
        if credit_file and credit_file.filename and allowed_file(credit_file.filename):
            filename = secure_filename(credit_file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            try:
                credit_file.save(filepath)
                log.info(f"Saved credit file: {filename}")
                credit_transactions = parser.parse_credit_csv(filepath)
                all_transactions.extend(credit_transactions)
                files_processed.append(filename)
                log.info(f"Parsed {len(credit_transactions)} transactions from {filename}")
            except Exception as e:
                log.error(f"Error processing credit file {filename}: {e}", exc_info=True)
                errors.append(f"Error processing {filename}: {e}")
            finally:
                 # Clean up uploaded file after processing
                 if os.path.exists(filepath):
                     try: os.remove(filepath); log.info(f"Removed uploaded file: {filepath}")
                     except OSError as e: log.error(f"Error removing uploaded file {filepath}: {e}")

        # Save all parsed transactions to DB
        saved_count = 0
        if all_transactions:
            try:
                database.save_transactions(all_transactions)
                saved_count = len(all_transactions) # Assume all were saved if no exception
            except Exception as e:
                log.error(f"Error saving transactions to database: {e}", exc_info=True)
                errors.append(f"Database error: Failed to save transactions.")

        # --- LLM Category Suggestion Step ---
        llm_suggestions_count = 0
        if saved_count > 0 and not errors: # Only run if initial save seemed okay
            try:
                log.info("Starting LLM category suggestion process...")
                uncategorized_tx = [tx for tx in all_transactions if tx.category == 'Uncategorized']
                log.info(f"Found {len(uncategorized_tx)} transactions initially marked as 'Uncategorized'.")

                if uncategorized_tx:
                    # Define the list of valid categories the LLM can choose from
                    # TODO: Get this list dynamically, e.g., from a config file or predefined set
                    valid_categories = [
                        "Food", "Groceries", "Restaurants", "Coffee Shops",
                        "Shopping", "Clothing", "Electronics", "Home Goods",
                        "Utilities", "Electricity", "Gas", "Water", "Internet", "Phone",
                        "Rent", "Mortgage", "Housing",
                        "Transportation", "Gas", "Public Transport", "Car Maintenance", "Parking",
                        "Health & Wellness", "Gym", "Pharmacy", "Doctor",
                        "Entertainment", "Movies", "Games", "Subscriptions", "Books",
                        "Travel", "Flights", "Hotels", "Vacation",
                        "Income", "Salary", "Freelance", "Other Income",
                        "Transfers", "Payments", "Investment", "Savings",
                        "Personal Care", "Gifts", "Charity", "Education",
                        "Business Expense", "Miscellaneous", "Ignore", "Uncategorized"
                    ]

                    # Combine existing rules for context (optional)
                    # Be mindful of prompt length limits
                    context_rules = {}
                    context_rules.update(parser.VENDOR_RULES)
                    context_rules.update(parser.USER_RULES) # User rules override vendor rules here

                    # Call the LLM service
                    suggested_rules_map = llm_service.suggest_categories_for_transactions(
                        transactions_to_categorize=uncategorized_tx,
                        valid_categories=valid_categories,
                        existing_rules=context_rules, # Provide context
                        # sample_size=10 # Optional: Limit during testing
                    )

                    # Save the suggested rules
                    if suggested_rules_map:
                        log.info(f"Received {len(suggested_rules_map)} category suggestions from LLM. Saving to llm_rules.json...")
                        for desc_key, suggested_cat in suggested_rules_map.items():
                            parser.save_llm_rule(desc_key, suggested_cat)
                            llm_suggestions_count += 1
                        log.info(f"Finished saving {llm_suggestions_count} LLM rules.")
                    else:
                        log.info("LLM did not provide any new category suggestions.")
                else:
                    log.info("No 'Uncategorized' transactions found to send to LLM.")

            except Exception as llm_error:
                log.error(f"Error during LLM category suggestion: {llm_error}", exc_info=True)
                # Append to errors, but don't necessarily fail the whole upload
                errors.append(f"LLM Suggestion Error: {llm_error}")
        # --- End LLM Step ---


        # --- Final Response ---
        final_message = f"Successfully processed and saved {saved_count} transactions from {len(files_processed)} files."
        if llm_suggestions_count > 0:
            final_message += f" Generated and saved {llm_suggestions_count} AI category suggestions."

        if not files_processed and not errors:
             return jsonify({"error": "No valid files uploaded or processed."}), 400
        elif errors:
            # Include LLM errors in the response if they occurred
            return jsonify({
                "message": final_message + " Encountered errors.",
                "files_processed": files_processed,
                "errors": errors
            }), 500 # Return 500 if any error occurred
        else:
            return jsonify({
                "message": final_message,
                "files_processed": files_processed
            }), 201
    # --- End POST Logic ---

    # If GET request, show a simple upload form
    return '''
    <!doctype html>
    <title>Upload CSV Files</title>
    <h1>Upload Chase Checking and/or Credit Card CSV</h1>
    <form method=post enctype=multipart/form-data>
      <label for="checking_file">Checking CSV:</label>
      <input type=file name=checking_file id="checking_file"><br><br>
      <label for="credit_file">Credit Card CSV:</label>
      <input type=file name=credit_file id="credit_file"><br><br>
      <input type=submit value=Upload>
    </form>
    '''

@app.route('/transactions', methods=['GET'])
def get_transactions():
    """Retrieves transactions, optionally filtered by date range and category."""
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    category = request.args.get('category')
    log.info(f"Received /transactions request with params: start={start_date_str}, end={end_date_str}, category={category}")

    # --- Add Date Validation ---
    start_date_obj = None
    end_date_obj = None
    try:
        if start_date_str: start_date_obj = dt.datetime.strptime(start_date_str, '%Y-%m-%d').date()
        if end_date_str: end_date_obj = dt.datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except ValueError:
         log.error(f"Invalid date format in request parameters.")
         return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    if start_date_obj and end_date_obj and start_date_obj > end_date_obj:
        log.error(f"Start date ({start_date_str}) cannot be after end date ({end_date_str}).")
        return jsonify({"error": "start_date cannot be after end_date."}), 400
    # --- End Date Validation ---

    try:
        transactions = database.get_all_transactions(
            start_date=start_date_str, # Pass string directly
            end_date=end_date_str,     # Pass string directly
            category=category
        )
        # Convert transactions to dictionary format for JSON response
        transactions_dict = [tx.to_dict() for tx in transactions]
        log.info(f"Returning {len(transactions_dict)} transactions.")
        return jsonify(transactions_dict)
    except Exception as e:
        log.error(f"Error retrieving transactions from database: {e}", exc_info=True)
        return jsonify({"error": "Failed to retrieve transactions."}), 500

@app.route('/transactions/<int:transaction_id>/category', methods=['PUT'])
def update_category(transaction_id):
    """Updates the category for a specific transaction."""
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    new_category = data.get('category')

    if not new_category or not isinstance(new_category, str):
        return jsonify({"error": "Missing or invalid 'category' field in request body"}), 400

    log.info(f"Received request to update category for ID {transaction_id} to '{new_category}'")

    try:
        # Optional: Get the transaction first to extract description for user rule
        # TODO: Implement database.get_transaction_by_id for efficiency
        transactions = database.get_all_transactions() # Inefficient, gets all transactions
        transaction_to_update = next((tx for tx in transactions if tx.id == transaction_id), None)

        if not transaction_to_update:
             log.warning(f"Transaction ID {transaction_id} not found for category update.")
             return jsonify({"error": "Transaction not found"}), 404

        # Update in database
        success = database.update_transaction_category(transaction_id, new_category)

        if success:
            # Save user rule based on the update
            # Use the RAW description if available, otherwise the cleaned one
            desc_for_rule = transaction_to_update.raw_description or transaction_to_update.description
            if desc_for_rule:
                parser.add_user_rule(desc_for_rule, new_category)
                log.info(f"Saved user rule based on raw description '{desc_for_rule}' -> '{new_category}'")
            else:
                 log.warning(f"Transaction ID {transaction_id} has no description, cannot save user rule.")

            return jsonify({"message": f"Category for transaction {transaction_id} updated to '{new_category}'"}), 200
        else:
            # update_transaction_category already logged the warning/error
            return jsonify({"error": "Failed to update category"}), 500 # Or 404 if appropriate
    except Exception as e:
        log.error(f"Unexpected error during category update for ID {transaction_id}: {e}", exc_info=True)
        return jsonify({"error": "An unexpected error occurred."}), 500


# --- Analysis Endpoints ---

@app.route('/summary', methods=['GET'])
def get_summary():
    """Calculates and returns a financial summary."""
    # Default date range: last 2 full years from today
    today = dt.date.today()
    default_end_date = today
    default_start_date = today - relativedelta(years=2)

    # Allow overriding with query parameters
    start_date_query = request.args.get('start_date')
    end_date_query = request.args.get('end_date')

    start_date = parse_date_param(start_date_query, default_start_date)
    end_date = parse_date_param(end_date_query, default_end_date)

    # Ensure start is not after end
    if start_date and end_date and start_date > end_date:
         log.error(f"Summary request error: Start date ({start_date.isoformat()}) cannot be after end date ({end_date.isoformat()}).")
         return jsonify({"error": "start_date cannot be after end_date."}), 400

    start_date_str = start_date.isoformat() if start_date else None
    end_date_str = end_date.isoformat() if end_date else None

    log.info(f"Generating summary for period: {start_date_str} to {end_date_str}")

    try:
        # 1. Fetch transactions for the period
        transactions_for_period = database.get_all_transactions(
            start_date=start_date_str,
            end_date=end_date_str
        )
        # 2. Calculate summary stats using the correct function and transactions
        summary_data = insights.calculate_summary_insights(transactions_for_period)
        return jsonify(summary_data)
    except AttributeError:
        log.error(f"AttributeError: Could not find 'calculate_summary_insights' in module 'insights'. Check insights.py.", exc_info=True)
        return jsonify({"error": "Internal server error: Summary calculation function not found."}), 500
    except Exception as e:
        log.error(f"Error generating summary statistics: {e}", exc_info=True)
        return jsonify({"error": "Failed to generate summary."}), 500

@app.route('/trends/monthly_spending', methods=['GET'])
def get_monthly_trends():
    """Calculates and returns month-over-month spending trends."""
    # Get optional date range parameters
    start_date_query = request.args.get('start_date')
    end_date_query = request.args.get('end_date')

    # Parse dates if provided, otherwise insights function might use defaults
    start_date = None
    end_date = None
    if start_date_query:
        start_date = parse_date_param(start_date_query, None) # Pass None as default
        if not start_date: return jsonify({"error": "Invalid start_date format."}), 400
    if end_date_query:
        end_date = parse_date_param(end_date_query, None) # Pass None as default
        if not end_date: return jsonify({"error": "Invalid end_date format."}), 400

    if start_date and end_date and start_date > end_date:
         log.error(f"Trends request error: Start date ({start_date.isoformat()}) cannot be after end date ({end_date.isoformat()}).")
         return jsonify({"error": "start_date cannot be after end_date."}), 400

    log.info(f"Calculating monthly trends. Start: {start_date}, End: {end_date}")

    try:
        # Pass parsed date objects (or None) to the insights function
        trends_data = insights.calculate_monthly_spending_trends(start_date=start_date, end_date=end_date)
        return jsonify(trends_data)
    except Exception as e:
        log.error(f"Error calculating monthly trends: {e}", exc_info=True)
        return jsonify({"error": "Failed to calculate monthly trends."}), 500

# --- CORRECTED FUNCTION CALL ---
@app.route('/recurring', methods=['GET'])
def get_recurring():
    """Identifies potential recurring transactions."""
    # Allow overriding default parameters via query args
    try:
        min_occurrences = int(request.args.get('min_occurrences', 3))
        days_tolerance = int(request.args.get('days_tolerance', 5))
        amount_tolerance_percent = float(request.args.get('amount_tolerance_percent', 10.0))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid query parameter type for recurring detection."}), 400

    log.info(f"Detecting recurring transactions with params: min_occurrences={min_occurrences}, days_tolerance={days_tolerance}, amount_tolerance={amount_tolerance_percent}%")

    try:
        # --- UNCOMMENTED FETCHING TRANSACTIONS ---
        # Fetch all transactions (or filter by date if desired for recurring)
        all_transactions = database.get_all_transactions()
        # --- END UNCOMMENT ---

        # --- Use the correct function name and pass transactions ---
        recurring_data = insights.identify_recurring_transactions(
            transactions=all_transactions, # Pass the fetched transactions
            min_occurrences=min_occurrences,
            days_tolerance=days_tolerance,
            amount_tolerance_percent=amount_tolerance_percent
        )
        # --- End correction ---
        return jsonify(recurring_data)
    except AttributeError:
        # Specific handling for the case where the function might not exist
        log.error(f"AttributeError: Could not find 'identify_recurring_transactions' in module 'insights'. Check insights.py.", exc_info=True)
        return jsonify({"error": "Internal server error: Recurring transaction function not found."}), 500
    except Exception as e:
        log.error(f"Error detecting recurring transactions: {e}", exc_info=True)
        return jsonify({"error": "Failed to detect recurring transactions."}), 500
# --- END OF CORRECTED FUNCTION CALL ---

# --- LLM Endpoints ---

@app.route('/analysis/llm_summary', methods=['GET'])
def get_llm_summary():
    """Generates a financial summary using the LLM."""
    # Default date range: last 3 full months
    today = dt.date.today()
    # Calculate end of last month
    default_end_date = today.replace(day=1) - dt.timedelta(days=1)
    # Calculate start of month 3 months before end_date's month
    default_start_date = (default_end_date.replace(day=1) - relativedelta(months=2))

    # Allow overriding with query parameters
    start_date_query = request.args.get('start_date')
    end_date_query = request.args.get('end_date')

    start_date = parse_date_param(start_date_query, default_start_date)
    end_date = parse_date_param(end_date_query, default_end_date)

    if start_date and end_date and start_date > end_date:
        log.error(f"LLM Summary request error: Start date ({start_date.isoformat()}) cannot be after end date ({end_date.isoformat()}).")
        return jsonify({"error": "start_date cannot be after end_date."}), 400

    start_date_str = start_date.isoformat() if start_date else None
    end_date_str = end_date.isoformat() if end_date else None
    log.info(f"Generating LLM summary for period: {start_date_str} to {end_date_str}")

    try:
        # 1. Fetch transactions for the period
        transactions_for_period = database.get_all_transactions(
            start_date=start_date_str,
            end_date=end_date_str
        )
        # 2. Get summary stats using the correct function
        summary_data = insights.calculate_summary_insights(transactions_for_period)

        # 3. Get trends data for the relevant period
        trends_data = insights.calculate_monthly_spending_trends(start_date=start_date, end_date=end_date) # Pass dates

        # 4. Call LLM service
        llm_summary_text = llm_service.generate_financial_summary(summary_data, trends_data, start_date_str, end_date_str)

        return jsonify({"summary": llm_summary_text})
    except AttributeError:
        # Specific handling for the case where the function *still* might not exist
        log.error(f"AttributeError: Could not find function in 'insights' module. Check insights.py.", exc_info=True)
        return jsonify({"error": "Internal server error: Analysis function not found."}), 500
    except Exception as e:
        log.error(f"Error generating LLM summary: {e}", exc_info=True)
        return jsonify({"error": f"Failed to generate LLM summary: {type(e).__name__}"}), 500


@app.route('/ask', methods=['GET'])
def ask_llm():
    """Answers a financial question using the LLM, potentially with pre-calculation."""
    question = request.args.get('query')
    if not question:
        return jsonify({"error": "Missing 'query' parameter"}), 400

    # --- Date Range Handling (Consistent with /summary and /llm_summary) ---
    today = dt.date.today()
    # Default: last 2 years for broader context in Q&A
    default_end_date = today
    default_start_date = today - relativedelta(years=2)

    start_date_query = request.args.get('start_date')
    end_date_query = request.args.get('end_date')

    start_date = parse_date_param(start_date_query, default_start_date)
    end_date = parse_date_param(end_date_query, default_end_date)

    if start_date and end_date and start_date > end_date:
         log.error(f"/ask request error: Start date ({start_date.isoformat()}) cannot be after end date ({end_date.isoformat()}).")
         return jsonify({"error": "start_date cannot be after end_date."}), 400

    start_date_str = start_date.isoformat() if start_date else None
    end_date_str = end_date.isoformat() if end_date else None
    log.info(f"Received /ask request for period {start_date_str} to {end_date_str}. Query: '{question}'")
    # --- End Date Range Handling ---

    pre_calculated_result: Optional[Decimal] = None
    calculation_performed = False

    # --- Simple Keyword-Based Calculation Detection ---
    q_lower = question.lower()
    try:
        # Check for Income Calculation
        # More robust: Use regex or simple NLP later
        if ("income" in q_lower and ("total" in q_lower or "how much" in q_lower or "sum" in q_lower)) or \
           ("much did i earn" in q_lower):
            log.info("Detected potential income calculation request.")
            # Ensure start/end dates are strings for the database function
            if start_date_str and end_date_str:
                pre_calculated_result = database.calculate_total_for_period(
                    start_date=start_date_str,
                    end_date=end_date_str,
                    transaction_type='income',
                    exclude_categories=['Payments', 'Transfers'] # Crucial exclusion
                )
                calculation_performed = True
                log.info(f"Pre-calculated income result: {pre_calculated_result}")
            else:
                log.warning("Cannot perform calculation without valid start/end dates.")


        # Check for Spending Calculation (General or by Category)
        # More robust: Use regex or simple NLP later
        elif ("spending" in q_lower or "spent" in q_lower or "cost" in q_lower) and \
             ("total" in q_lower or "how much" in q_lower or "sum" in q_lower):
            log.info("Detected potential spending calculation request.")
            # Try to extract category (very basic)
            category_to_calc = None
            # Example: "how much spent on Food" -> category_to_calc = "Food"
            # This needs significant improvement for real-world use
            words = q_lower.split()
            if "on" in words:
                try:
                    on_index = words.index("on")
                    if on_index + 1 < len(words):
                         # Capitalize potential category name to match DB storage
                         potential_cat = words[on_index + 1].capitalize()
                         # TODO: Check if potential_cat is a valid category?
                         category_to_calc = potential_cat
                         log.info(f"Extracted potential category for spending calculation: {category_to_calc}")
                except ValueError:
                    pass # "on" not found

            if start_date_str and end_date_str:
                pre_calculated_result = database.calculate_total_for_period(
                    start_date=start_date_str,
                    end_date=end_date_str,
                    category=category_to_calc, # Pass category if found
                    transaction_type='spending'
                )
                calculation_performed = True
                # Spending is negative, format appropriately if needed for LLM
                log.info(f"Pre-calculated spending result: {pre_calculated_result}")
            else:
                 log.warning("Cannot perform calculation without valid start/end dates.")


    except Exception as calc_error:
        log.error(f"Error during pre-calculation attempt: {calc_error}", exc_info=True)
        # Decide if you want to proceed without calculation or return an error
        # Proceeding allows LLM to try, but might give wrong answer if calculation was intended
        calculation_performed = False # Ensure we know calculation failed
        pre_calculated_result = None
    # --- End Calculation Detection ---


    try:
        # 1. Fetch transactions for the period (LLM still needs context)
        transactions = database.get_all_transactions(
            start_date=start_date_str,
            end_date=end_date_str
        )
        # 2. Calculate summary stats using the correct function
        # Pass the already fetched transactions to avoid hitting DB again
        summary_data = insights.calculate_summary_insights(transactions)

        # 3. Call LLM service, passing the pre-calculated result if available
        llm_answer = llm_service.answer_financial_question(
            question=question,
            transactions=transactions,
            summary_data=summary_data,
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            pre_calculated_result=pre_calculated_result # Pass the result
        )

        log.info("LLM answer generated successfully.")
        return jsonify({"question": question, "answer": llm_answer})
    except AttributeError as attr_err:
        # Check if the error is specifically about calculate_summary_insights
        if 'calculate_summary_insights' in str(attr_err):
            log.error(f"AttributeError: Could not find 'calculate_summary_insights' in module 'insights'. Check insights.py.", exc_info=True)
            return jsonify({"error": "Internal server error: Summary calculation function not found."}), 500
        else:
            # Handle other potential AttributeErrors
            log.error(f"AttributeError during LLM question answering: {attr_err}", exc_info=True)
            return jsonify({"error": f"Failed to get answer from LLM: AttributeError"}), 500
    except Exception as e:
        log.error(f"Error during LLM question answering: {e}", exc_info=True)
        return jsonify({"error": f"Failed to get answer from LLM: {type(e).__name__}"}), 500


# --- Favicon Route (Optional) ---
@app.route('/favicon.ico')
def favicon():
    # Serve a favicon if you have one in a 'static' folder
    # Ensure you have a 'static' folder next to app.py with favicon.ico inside
    static_folder = os.path.join(app.root_path, 'static')
    favicon_path = os.path.join(static_folder, 'favicon.ico')
    if os.path.exists(favicon_path):
        return send_from_directory(static_folder, 'favicon.ico', mimetype='image/vnd.microsoft.icon')
    else:
        # Return a 404 if favicon doesn't exist
        return '', 404

# --- Main Execution ---
if __name__ == '__main__':
    # Make sure database is initialized before running
    database.initialize_database()
    # Run the Flask app
    # Use host='0.0.0.0' to make it accessible on your network
    # Use debug=True for development (provides auto-reloading and debugger)
    # Use debug=False for production
    app.run(host=app.config.get('HOST', '127.0.0.1'),
            port=app.config.get('PORT', 5001),
            debug=app.config.get('DEBUG', True))

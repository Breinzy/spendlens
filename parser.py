# parser.py
import csv
import json
import logging
import os
from decimal import Decimal, InvalidOperation
import datetime as dt
from dateutil.parser import parse as dateutil_parse, ParserError as DateParserError
from typing import List, Dict, Optional, Any, Union, TextIO, Set
import io

# --- Constants ---
DUMMY_CLI_USER_ID = "cli_report_user"

# --- Database Interaction (with fallback for standalone testing) ---
try:
    import database_supabase as database

    log_parser_db_status = "database_supabase imported successfully."
except ModuleNotFoundError:
    class DummyDB:
        def __init__(self): self._log = logging.getLogger('parser_dummy_db'); self._log.warning("Using DummyDB.")

        def get_user_rules(self, user_id: str) -> Dict[str, str]: self._log.debug(
            f"DummyDB: get_user_rules({user_id})"); return {}

        def get_llm_rules(self, user_id: str) -> Dict[str, str]: self._log.debug(
            f"DummyDB: get_llm_rules({user_id})"); return {}

        def save_user_rule(self, user_id: str, key: str, cat: str): self._log.debug(
            f"DummyDB: save_user_rule({user_id}, '{key}', '{cat}')")

        def save_llm_rule(self, user_id: str, key: str, cat: str): self._log.debug(
            f"DummyDB: save_llm_rule({user_id}, '{key}', '{cat}')")


    database = DummyDB()
    log_parser_db_status = "Failed to import 'database_supabase'. Using DummyDB."

# --- Logging Setup ---
log = logging.getLogger('parser')
try:
    from config import settings

    log.setLevel(logging.DEBUG if settings.DEBUG_MODE else logging.INFO)
except ImportError:
    log.setLevel(logging.INFO)
    print("WARN: Could not import config settings in parser.py, defaulting log level.")

if not log.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [%(name)s:%(module)s:%(funcName)s:%(lineno)d] - %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)
log.info(f"Parser module initialized. DB status: {log_parser_db_status}")

# --- Global Vendor Rules ---
VENDOR_RULES_FILE = 'vendors.json'
VENDOR_RULES: Dict[str, str] = {}


# --- Transaction Data Class ---
class Transaction:
    def __init__(self, id: Optional[int] = None, user_id: str = "", date: Optional[dt.date] = None,
                 description: Optional[str] = None, amount: Optional[Decimal] = None, category: Optional[str] = None,
                 transaction_type: Optional[str] = None, source_account_type: Optional[str] = None,
                 source_filename: Optional[str] = None, raw_description: Optional[str] = None,
                 client_name: Optional[str] = None, invoice_id: Optional[str] = None,
                 project_id: Optional[str] = None, payout_source: Optional[str] = None,
                 transaction_origin: Optional[str] = None,
                 data_context: Optional[str] = 'business',
                 rate: Optional[Decimal] = None, quantity: Optional[Decimal] = None,
                 invoice_status: Optional[str] = None, date_paid: Optional[dt.date] = None,
                 created_at: Optional[dt.datetime] = None, updated_at: Optional[dt.datetime] = None):
        self.id = id
        self.user_id = user_id
        self.date = date
        self.description = description
        self.amount = amount
        self.category = category
        self.transaction_type = transaction_type
        self.source_account_type = source_account_type
        self.source_filename = source_filename
        self.raw_description = raw_description if raw_description else description
        self.client_name = client_name
        self.invoice_id = invoice_id
        self.project_id = project_id
        self.payout_source = payout_source
        self.transaction_origin = transaction_origin
        self.data_context = data_context
        self.rate = rate
        self.quantity = quantity
        self.invoice_status = invoice_status
        self.date_paid = date_paid
        self.created_at = created_at
        self.updated_at = updated_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            k: (v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else str(v) if isinstance(v, Decimal) else v)
            for k, v in self.__dict__.items() if v is not None
        }


# --- Utility Functions ---
def allowed_file(filename: str, allowed_extensions: Optional[Set[str]] = None) -> bool:
    if allowed_extensions is None:
        allowed_extensions = {'csv'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions


def load_vendor_rules(filepath: str) -> Dict[str, str]:
    rules: Dict[str, str] = {}
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            if not content.strip():
                log.info(f"Vendor rules file '{filepath}' is empty.")
                return {}
            rules = json.loads(content)
            log.info(f"Loaded {len(rules)} vendor rules from '{filepath}'.")
            return {k.lower().strip(): v for k, v in rules.items()}
        except json.JSONDecodeError as jde:
            log.error(f"Error decoding JSON from vendor rules file '{filepath}': {jde}", exc_info=True)
        except Exception as e:
            log.error(f"Error loading vendor rules from '{filepath}': {e}", exc_info=True)
    else:
        log.warning(f"Vendor rules file not found: '{filepath}'. No vendor rules loaded.")
    return {}


VENDOR_RULES = load_vendor_rules(VENDOR_RULES_FILE)


def add_user_rule(user_id: str, description_fragment: str, category: str):
    if user_id == DUMMY_CLI_USER_ID:
        log.info(f"CLI mode: Skipping save_user_rule for '{description_fragment}' -> '{category}'")
        return
    if not description_fragment or not category:
        log.warning(f"User {user_id}: Attempt to save empty user rule or category.")
        return
    try:
        database.save_user_rule(user_id, description_fragment.lower().strip(), category)
    except Exception as e:
        log.error(f"Failed to save user rule for user {user_id} ('{description_fragment}' -> '{category}'): {e}",
                  exc_info=True)


def save_llm_rule(user_id: str, description_fragment: str, category: str):
    if user_id == DUMMY_CLI_USER_ID:
        log.info(f"CLI mode: Skipping save_llm_rule for '{description_fragment}' -> '{category}'")
        return
    if not description_fragment or not category:
        log.warning(f"User {user_id}: Attempt to save empty LLM rule or category.")
        return
    try:
        database.save_llm_rule(user_id, description_fragment.lower().strip(), category)
    except Exception as e:
        log.error(f"Failed to save LLM rule for user {user_id} ('{description_fragment}' -> '{category}'): {e}",
                  exc_info=True)


# --- MODIFIED: categorize_transaction - Now just a placeholder, logic moved ---
# This function is kept for potential future use but is bypassed for 'business' context
def categorize_transaction_with_rules(
        user_id: str,
        description: str,
        user_rules: Dict[str, str],
        llm_rules: Dict[str, str]
) -> str:
    """
    Categorizes a transaction based on pre-fetched user, vendor, and LLM rules.
    Does NOT query the database internally.
    """
    if not description:
        return 'Uncategorized'
    desc_lower = description.lower().strip()

    # Priority: User Rules
    if user_id != DUMMY_CLI_USER_ID:
        for key in sorted(user_rules.keys(), key=len, reverse=True):
            if key in desc_lower:
                log.debug(f"User rule match: '{key}' for description '{desc_lower}' -> '{user_rules[key]}'")
                return user_rules[key]

    # Priority: Vendor Rules
    for key in sorted(VENDOR_RULES.keys(), key=len, reverse=True):
        if key in desc_lower:
            log.debug(f"Vendor rule match: '{key}' for description '{desc_lower}' -> '{VENDOR_RULES[key]}'")
            return VENDOR_RULES[key]

    # Priority: LLM Rules (if applicable)
    if user_id != DUMMY_CLI_USER_ID:
        for key in sorted(llm_rules.keys(), key=len, reverse=True):
            if key in desc_lower:
                log.debug(f"LLM rule match: '{key}' for description '{desc_lower}' -> '{llm_rules[key]}'")
                return llm_rules[key]

    log.debug(f"No rule match for '{description}'. Defaulting to Uncategorized.")
    return 'Uncategorized'


# --- END MODIFIED ---

def _get_text_stream(user_id: str, file_like_object: Union[io.BytesIO, TextIO], filename: str,
                     parser_name: str) -> TextIO:
    if isinstance(file_like_object, io.BytesIO):
        try:
            return io.TextIOWrapper(file_like_object, encoding='utf-8-sig', errors='replace')
        except UnicodeDecodeError:
            log.warning(f"User {user_id}: UTF-8 decoding failed for '{filename}' in {parser_name}. Trying latin-1.")
            file_like_object.seek(0)
            return io.TextIOWrapper(file_like_object, encoding='latin-1', errors='replace')
    elif isinstance(file_like_object, io.TextIOBase):
        return file_like_object
    else:
        log.error(
            f"User {user_id}: Invalid file object type '{type(file_like_object)}' for '{filename}' in {parser_name}.")
        raise TypeError(f"{parser_name} expects a BytesIO or TextIOBase object, got {type(file_like_object)}.")


def parse_csv_with_schema(
        user_id: str,
        file_stream: TextIO,
        schema: Dict[str, Any],
        transaction_origin: str,
        source_filename: str,
        account_type: Optional[str] = None,
        data_context_override: Optional[str] = "business",
        project_id_override: Optional[str] = None
) -> List[Transaction]:
    transactions: List[Transaction] = []
    log.info(
        f"User {user_id}: Schema parsing START. Origin:'{transaction_origin}', File:'{source_filename}', Context:'{data_context_override}', Project:'{project_id_override}'")

    # Fetch rules only if needed (not business context for now)
    user_rules_map: Dict[str, str] = {}
    llm_rules_map: Dict[str, str] = {}
    apply_categorization_rules = (data_context_override != 'business')  # Only apply rules if not business context

    if apply_categorization_rules and user_id != DUMMY_CLI_USER_ID:
        try:
            user_rules_map = database.get_user_rules(user_id)
            llm_rules_map = database.get_llm_rules(user_id)
            log.info(
                f"User {user_id}: Pre-fetched {len(user_rules_map)} user rules and {len(llm_rules_map)} LLM rules for '{source_filename}' (Context: {data_context_override}).")
        except Exception as db_err:
            log.error(f"User {user_id}: Failed to pre-fetch rules for '{source_filename}': {db_err}", exc_info=True)
            # Continue without rules if DB fetch fails
            apply_categorization_rules = False

    try:
        skip_lines = schema.get("skip_initial_lines", 0)
        if skip_lines > 0:
            log.debug(f"Skipping {skip_lines} initial lines.")
            for _ in range(skip_lines):
                next(file_stream)

        reader = csv.DictReader(file_stream)
        if not reader.fieldnames:
            raise ValueError(f"CSV file '{source_filename}' appears empty/headerless.")

        csv_headers_map = {name.lower().strip(): name for name in reader.fieldnames}
        log.debug(f"User {user_id}: Normalized CSV Headers Map: {csv_headers_map}")

        def get_actual_col_name(keys: List[str], field_name_for_log: str) -> Optional[str]:
            log.debug(
                f"get_actual_col_name called for field '{field_name_for_log}' with possible keys: {keys} (Origin: {transaction_origin})")
            if not isinstance(keys, list):
                log.warning(
                    f"Schema issue for field '{field_name_for_log}': 'keys' is not a list: {keys}. Origin: {transaction_origin}")
                return None

            for k_item in keys:
                if not isinstance(k_item, str):
                    log.warning(
                        f"Schema issue for field '{field_name_for_log}': Non-string key '{k_item}' found in list: {keys}. Origin: {transaction_origin}")
                    continue

                current_norm_k = k_item.lower().strip()
                if current_norm_k in csv_headers_map:
                    log.debug(
                        f"Field '{field_name_for_log}': Found match '{k_item}' (normalized: '{current_norm_k}') in CSV headers.")
                    return csv_headers_map[current_norm_k]
            log.debug(f"Field '{field_name_for_log}': No match found in CSV headers for keys: {keys}.")
            return None

        # Get column names using the helper
        date_col = get_actual_col_name(schema.get("date_fields", []), "date_fields")
        desc_col = get_actual_col_name(schema.get("description_fields", []), "description_fields")
        amount_col = get_actual_col_name(schema.get("amount_fields", []), "amount_fields")
        rate_col = get_actual_col_name(schema.get("rate_fields", []), "rate_fields")
        quantity_col = get_actual_col_name(schema.get("quantity_fields", []), "quantity_fields")
        invoice_status_col = get_actual_col_name(schema.get("invoice_status_fields", []), "invoice_status_fields")
        date_paid_col = get_actual_col_name(schema.get("date_paid_fields", []), "date_paid_fields")
        type_col = get_actual_col_name(schema.get("transaction_type_fields", []), "transaction_type_fields")
        category_col_csv = get_actual_col_name(schema.get("category_fields", []), "category_fields")
        client_name_col = get_actual_col_name(schema.get("client_name_fields", []), "client_name_fields")
        invoice_id_col = get_actual_col_name(schema.get("invoice_id_fields", []), "invoice_id_fields")
        project_id_col_csv = get_actual_col_name(schema.get("project_id_fields", []), "project_id_fields")
        payout_source_col_name = get_actual_col_name(schema.get("payout_source_fields", []), "payout_source_fields")
        duration_col = get_actual_col_name(schema.get("duration_fields", []), "duration_fields")
        billable_rate_col = get_actual_col_name(schema.get("billable_rate_fields", []), "billable_rate_fields")

        # Check for essential columns
        required_map = {"Date": date_col, "Description": desc_col}
        if transaction_origin not in ['clockify_log', 'toggl_log'] and not amount_col:
            required_map["Amount"] = amount_col
        elif transaction_origin in ['clockify_log', 'toggl_log'] and not amount_col and not (
                duration_col and billable_rate_col):
            raise ValueError(f"Time log '{source_filename}' missing Amount or (Duration and Billable Rate).")

        missing_essentials = [k for k, v in required_map.items() if not v]
        if missing_essentials:
            raise ValueError(
                f"Missing essential columns in '{source_filename}' for schema '{transaction_origin}': {', '.join(missing_essentials)}. Available headers: {list(csv_headers_map.keys())}")

        date_format_hint = schema.get("date_format")
        processed_row_count = 0

        # Process each row
        for i, row_dict in enumerate(reader):
            row_num = i + 2 + skip_lines
            log.debug(f"User {user_id}: Processing row {row_num}...")
            try:
                # Extract basic fields
                date_str = row_dict.get(date_col) if date_col else None
                raw_desc_val = row_dict.get(desc_col, '') if desc_col else ''

                if not date_str or not raw_desc_val.strip():
                    log.warning(
                        f"Row {row_num}: Skipping due to missing date ('{date_str}') or description ('{raw_desc_val}').")
                    continue

                description = ' '.join(raw_desc_val.strip().split())

                try:
                    transaction_date = dateutil_parse(date_str.strip(),
                                                      dayfirst=False).date() if not date_format_hint else dt.datetime.strptime(
                        date_str.strip(), date_format_hint).date()
                except (DateParserError, ValueError, TypeError) as e:
                    log.warning(f"Row {row_num}: Skipping due to unparseable date '{date_str}': {e}.")
                    continue

                # Parse amount
                amount_val = Decimal('0')
                amount_str_from_csv = row_dict.get(amount_col) if amount_col else None
                if amount_str_from_csv:
                    try:
                        cleaned_amount_str = str(amount_str_from_csv).replace('$', '').replace(',', '').strip()
                        is_negative = cleaned_amount_str.startswith('(') and cleaned_amount_str.endswith(')')
                        if is_negative:
                            cleaned_amount_str = cleaned_amount_str[1:-1]
                        amount_val = Decimal(cleaned_amount_str)
                        if is_negative:
                            amount_val *= -1
                    except InvalidOperation:
                        log.warning(f"Row {row_num}: Invalid amount '{amount_str_from_csv}', using 0.")
                elif transaction_origin in ['clockify_log', 'toggl_log'] and duration_col and billable_rate_col:
                    # Calculate amount from time logs if amount column is missing
                    duration_str_tl = row_dict.get(duration_col)
                    billable_rate_str_tl = row_dict.get(billable_rate_col)
                    if duration_str_tl and billable_rate_str_tl:
                        try:
                            duration_decimal_hours = Decimal('0');
                            if ':' in duration_str_tl:
                                parts = duration_str_tl.split(':')
                                duration_decimal_hours = Decimal(parts[0]) + (Decimal(parts[1]) / 60) + (
                                            Decimal(parts[2]) / 3600) if len(parts) == 3 else Decimal(parts[0]) + (
                                            Decimal(parts[1]) / 60) if len(parts) == 2 else Decimal('0')
                            else:
                                duration_decimal_hours = Decimal(duration_str_tl)
                            rate_decimal_tl = Decimal(
                                str(billable_rate_str_tl).replace('$', '').replace(',', '').strip())
                            amount_val = duration_decimal_hours * rate_decimal_tl
                            log.debug(f"Row {row_num}: Calculated amount {amount_val} from time log.")
                        except (InvalidOperation, ValueError, TypeError) as time_calc_err:
                            log.warning(
                                f"Row {row_num}: Could not calculate amount from time log. Duration: '{duration_str_tl}', Rate: '{billable_rate_str_tl}'. Error: {time_calc_err}.")

                # Skip zero amount transactions unless allowed or non-billable time entry
                if amount_val == Decimal('0') and not schema.get("allow_zero_amount_transactions", False):
                    is_billable_col_name = get_actual_col_name(schema.get("is_billable_fields", []),
                                                               "is_billable_fields_check")
                    is_billable_str = "yes"
                    if is_billable_col_name and row_dict.get(is_billable_col_name) is not None:
                        is_billable_str = row_dict.get(is_billable_col_name, "yes").lower()

                    if transaction_origin in ['clockify_log', 'toggl_log'] and is_billable_str in ['no', 'false', '0',
                                                                                                   'non-billable',
                                                                                                   'non billable']:
                        log.debug(f"Row {row_num}: Skipping non-billable zero-amount time entry.")
                        continue
                    elif transaction_origin not in ['clockify_log', 'toggl_log']:
                        log.debug(f"Row {row_num}: Skipping zero-amount transaction (not a time log or not allowed).")
                        continue

                # Determine transaction type
                tx_type_csv_val = row_dict.get(type_col, "").strip() if type_col else None
                tx_type = tx_type_csv_val if tx_type_csv_val else ('CREDIT' if amount_val > 0 else 'DEBIT')

                # --- MODIFIED CATEGORY LOGIC ---
                category = 'Uncategorized'  # Default
                category_from_csv_val = row_dict.get(category_col_csv, "").strip() if category_col_csv else None
                if category_from_csv_val and category_from_csv_val.lower() != 'uncategorized':
                    category = category_from_csv_val
                    log.debug(f"Row {row_num}: Using category from CSV: '{category}'")
                elif apply_categorization_rules:
                    # Only apply rules if context is not 'business' (or rule fetching succeeded)
                    log.debug(
                        f"Row {row_num}: Context is '{data_context_override}', applying categorization rules for '{description}'...")
                    category = categorize_transaction_with_rules(user_id, description, user_rules_map, llm_rules_map)
                    log.debug(f"Row {row_num}: Rule-based categorization result: '{category}'")
                else:
                    # Keep default 'Uncategorized' for business context if not provided in CSV
                    log.debug(
                        f"Row {row_num}: Context is '{data_context_override}', skipping rule-based categorization. Defaulting to '{category}'.")

                # Override category for time tracking revenue if still uncategorized
                if transaction_origin in ['clockify_log',
                                          'toggl_log'] and category.lower() == 'uncategorized' and amount_val != Decimal(
                        '0'):
                    category = "Time Tracking Revenue"
                    log.debug(f"Row {row_num}: Setting category to '{category}' for time log.")
                # --- END MODIFIED CATEGORY LOGIC ---

                # Extract other optional fields
                client_name_val = row_dict.get(client_name_col, "").strip() if client_name_col else None
                invoice_id_val = row_dict.get(invoice_id_col, "").strip() if invoice_id_col else None
                payout_source_val_csv = row_dict.get(payout_source_col_name,
                                                     "").strip() if payout_source_col_name else None
                project_id_from_csv_val = row_dict.get(project_id_col_csv, "").strip() if project_id_col_csv else None
                final_project_id = project_id_from_csv_val if project_id_from_csv_val else project_id_override

                rate_val_decimal: Optional[Decimal] = None
                if rate_col and row_dict.get(rate_col):
                    try:
                        rate_val_decimal = Decimal(str(row_dict[rate_col]).replace('$', '').replace(',', '').strip())
                    except InvalidOperation:
                        log.warning(f"Row {row_num}: Invalid rate '{row_dict[rate_col]}'.")

                quantity_val_decimal: Optional[Decimal] = None
                if quantity_col and row_dict.get(quantity_col):
                    try:
                        quantity_val_decimal = Decimal(str(row_dict[quantity_col]).strip())
                    except InvalidOperation:
                        log.warning(f"Row {row_num}: Invalid quantity '{row_dict[quantity_col]}'.")

                invoice_status_str_val = row_dict.get(invoice_status_col,
                                                      "").strip().lower() if invoice_status_col else None

                date_paid_val_date: Optional[dt.date] = None
                if date_paid_col and row_dict.get(date_paid_col):
                    try:
                        date_paid_val_date = dateutil_parse(row_dict[date_paid_col].strip()).date()
                    except (DateParserError, ValueError, TypeError):
                        log.warning(f"Row {row_num}: Unparseable Date Paid '{row_dict[date_paid_col]}'.")

                # Create Transaction object
                transactions.append(Transaction(
                    user_id=user_id, date=transaction_date, description=description, amount=amount_val,
                    category=category, transaction_type=tx_type, source_account_type=account_type,
                    source_filename=source_filename, raw_description=raw_desc_val.strip(),
                    client_name=client_name_val, invoice_id=invoice_id_val, project_id=final_project_id,
                    payout_source=payout_source_val_csv, transaction_origin=transaction_origin,
                    data_context=data_context_override,
                    rate=rate_val_decimal, quantity=quantity_val_decimal,
                    invoice_status=invoice_status_str_val, date_paid=date_paid_val_date
                ))
                processed_row_count += 1

            except Exception as row_err:
                # Log errors processing individual rows, but continue with others
                log.error(
                    f"Row {row_num}: Error processing. File: '{source_filename}'. Raw row data: {row_dict}. Error: {row_err}",
                    exc_info=True)

        log.info(
            f"User {user_id}: Successfully finished processing {processed_row_count} rows from '{source_filename}'. Found {len(transactions)} valid transactions.")
        return transactions
    except ValueError as ve:  # Errors like missing essential columns
        log.error(f"User {user_id}: Value error parsing CSV '{source_filename}': {ve}", exc_info=True)
        raise  # Re-raise to be caught by the router
    except Exception as e:  # Other unexpected critical errors during setup or reading
        log.error(f"User {user_id}: Unexpected critical error parsing '{source_filename}': {e}", exc_info=True)
        raise RuntimeError(f"Failed to parse {source_filename} due to an unexpected error.") from e


# --- Specific Parser Functions ---
# Schemas are defined here. Ensure "transaction_type_fields" is appropriate for each.
CHASE_COMMON_SCHEMA = {
    "date_fields": ["Transaction Date", "Posting Date"],
    "description_fields": ["Description"],
    "amount_fields": ["Amount"],
    "transaction_type_fields": ["Type"],
    "category_fields": ["Category"],
    "date_format": "%m/%d/%Y"
}


def parse_checking_csv(user_id: str, file_obj: Union[io.BytesIO, TextIO], filename: str,
                       data_context_override: str = "business", project_id_override: Optional[str] = None) -> List[
    Transaction]:
    s = _get_text_stream(user_id, file_obj, filename, "parse_checking_csv")
    return parse_csv_with_schema(user_id, s, CHASE_COMMON_SCHEMA, 'chase_checking', filename, 'checking',
                                 data_context_override, project_id_override)


def parse_credit_csv(user_id: str, file_obj: Union[io.BytesIO, TextIO], filename: str,
                     data_context_override: str = "business", project_id_override: Optional[str] = None) -> List[
    Transaction]:
    s = _get_text_stream(user_id, file_obj, filename, "parse_credit_csv")
    return parse_csv_with_schema(user_id, s, CHASE_COMMON_SCHEMA, 'chase_credit', filename, 'credit',
                                 data_context_override, project_id_override)


STRIPE_PAYOUTS_SCHEMA = {
    "date_fields": ["created", "created_utc", "available_on", "available_on_utc", "date", "Arrival Date"],
    "description_fields": ["description", "summary", "charge id", "payment intent id", "Description", "Source"],
    "amount_fields": ["net", "amount", "Net", "Amount"],
    "transaction_type_fields": ["type", "Type"],
    "invoice_id_fields": ["charge_id", "payment_intent_id", "source_id", "invoice", "id", "Charge ID"],
    "payout_source_fields": ["source_type", "card_brand", "Network"],
    "client_name_fields": ["customer_facing_descriptor", "customer_email", "customer_name", "metadata.client_name",
                           "Customer Name", "Customer Email"],
    "date_format": None,
}


def parse_stripe_csv(user_id: str, file_obj: Union[io.BytesIO, TextIO], filename: str,
                     data_context_override: str = "business", project_id_override: Optional[str] = None) -> List[
    Transaction]:
    s = _get_text_stream(user_id, file_obj, filename, "parse_stripe_csv")
    return parse_csv_with_schema(user_id, s, STRIPE_PAYOUTS_SCHEMA, 'stripe_transaction', filename, None,
                                 data_context_override, project_id_override)


PAYPAL_TRANSACTIONS_SCHEMA = {
    "date_fields": ["Date"],
    "description_fields": ["Name", "Item Title", "Subject", "Note", "Type"],
    "amount_fields": ["Net", "Gross"],
    "transaction_type_fields": ["Type"],
    "invoice_id_fields": ["Invoice Number", "Transaction ID"],
    "client_name_fields": ["Name", "From Email Address"],
    "date_format": "%m/%d/%Y"
}


def parse_paypal_csv(user_id: str, file_obj: Union[io.BytesIO, TextIO], filename: str,
                     data_context_override: str = "business", project_id_override: Optional[str] = None) -> List[
    Transaction]:
    s = _get_text_stream(user_id, file_obj, filename, "parse_paypal_csv")
    return parse_csv_with_schema(user_id, s, PAYPAL_TRANSACTIONS_SCHEMA, 'paypal_transaction', filename, None,
                                 data_context_override, project_id_override)


GENERIC_INVOICE_SCHEMA = {
    "date_fields": ["Date Issued", "Invoice Date", "Payment Date", "Date"],
    "description_fields": ["Item Description", "Item Name", "Description", "Line Item Description", "Service Rendered",
                           "Memo"],
    "amount_fields": ["Line Total", "Total Amount", "Amount Paid", "Net Amount", "Total", "Amount"],
    "rate_fields": ["Rate", "Unit Price", "Price"],
    "quantity_fields": ["Quantity", "Qty", "Hours"],
    "client_name_fields": ["Client Name", "Customer", "Vendor Name", "Billed To", "Client"],
    "invoice_id_fields": ["Invoice #", "Invoice ID", "Reference Number", "Number", "Invoice Number"],
    "project_id_fields": ["Project Name", "Project Code", "Job", "Project"],
    "transaction_type_fields": ["Type", "Transaction Type"],
    "invoice_status_fields": ["Invoice Status", "Status"],
    "date_paid_fields": ["Date Paid", "Payment Date"],
    "date_format": None
}


def parse_invoice_csv(user_id: str, file_obj: Union[io.BytesIO, TextIO], filename: str,
                      data_context_override: str = "business", project_id_override: Optional[str] = None) -> List[
    Transaction]:
    s = _get_text_stream(user_id, file_obj, filename, "parse_invoice_csv")
    return parse_csv_with_schema(user_id, s, GENERIC_INVOICE_SCHEMA, 'invoice_import', filename, None,
                                 data_context_override, project_id_override)


FRESHBOOKS_INVOICE_SCHEMA = {
    "date_fields": ["Date Issued", "Date"],
    "description_fields": ["Item Description", "Item Name", "Description"],
    "amount_fields": ["Line Total", "Amount"],
    "rate_fields": ["Rate"],
    "quantity_fields": ["Quantity"],
    "client_name_fields": ["Client Name", "Client"],
    "invoice_id_fields": ["Invoice #", "Invoice Number"],
    "project_id_fields": ["Project Name", "Project"],
    "invoice_status_fields": ["Invoice Status", "Status"],
    "date_paid_fields": ["Date Paid"],
    "transaction_type_fields": [],
    "date_format": "%Y-%m-%d",
    "allow_zero_amount_transactions": True
}


def parse_freshbooks_csv(user_id: str, file_obj: Union[io.BytesIO, TextIO], filename: str,
                         data_context_override: str = "business", project_id_override: Optional[str] = None) -> List[
    Transaction]:
    log.info(
        f"User {user_id}: Parsing FreshBooks CSV '{filename}'. Context: {data_context_override}, Project: {project_id_override}")
    text_stream = _get_text_stream(user_id, file_obj, filename, "parse_freshbooks_csv")
    return parse_csv_with_schema(user_id, text_stream, FRESHBOOKS_INVOICE_SCHEMA, 'freshbooks_invoice', filename, None,
                                 data_context_override, project_id_override)


CLOCKIFY_SCHEMA = {
    "date_fields": ["Start Date", "Date"],
    "description_fields": ["Description", "Task"],
    "amount_fields": ["Billable Amount (USD)", "Billable Amount"],
    "billable_rate_fields": ["Billable Rate (USD)", "Billable Rate"],
    "duration_fields": ["Duration (decimal)", "Duration (h)"],
    "client_name_fields": ["Client"],
    "project_id_fields": ["Project"],
    "is_billable_fields": ["Billable"],
    "transaction_type_fields": [],
    "date_format": "%Y-%m-%d",
    "allow_zero_amount_transactions": True
}


def parse_clockify_csv(user_id: str, file_obj: Union[io.BytesIO, TextIO], filename: str,
                       data_context_override: str = "business", project_id_override: Optional[str] = None) -> List[
    Transaction]:
    log.info(
        f"User {user_id}: Parsing Clockify CSV '{filename}'. Context: {data_context_override}, Project: {project_id_override}")
    text_stream = _get_text_stream(user_id, file_obj, filename, "parse_clockify_csv")
    return parse_csv_with_schema(user_id, text_stream, CLOCKIFY_SCHEMA, 'clockify_log', filename, None,
                                 data_context_override, project_id_override)


TOGGL_SCHEMA = {
    "date_fields": ["Start date"],
    "description_fields": ["Description", "Task"],
    "amount_fields": ["Amount (USD)", "Amount"],
    "billable_rate_fields": ["Rate (USD)", "Rate"],
    "duration_fields": ["Duration"],
    "client_name_fields": ["Client"],
    "project_id_fields": ["Project"],
    "is_billable_fields": ["Billable"],
    "transaction_type_fields": [],
    "date_format": "%Y-%m-%d",
    "allow_zero_amount_transactions": True
}


def parse_toggl_csv(user_id: str, file_obj: Union[io.BytesIO, TextIO], filename: str,
                    data_context_override: str = "business", project_id_override: Optional[str] = None) -> List[
    Transaction]:
    log.info(
        f"User {user_id}: Parsing Toggl CSV '{filename}'. Context: {data_context_override}, Project: {project_id_override}")
    text_stream = _get_text_stream(user_id, file_obj, filename, "parse_toggl_csv")
    return parse_csv_with_schema(user_id, text_stream, TOGGL_SCHEMA, 'toggl_log', filename, None, data_context_override,
                                 project_id_override)


if __name__ == '__main__':
    log.info("parser.py executed directly for testing.")
    test_user_id_cli = DUMMY_CLI_USER_ID
    test_files_dir = "temp_parser_test_files"
    os.makedirs(test_files_dir, exist_ok=True)

    dummy_freshbooks_content = (
        "Client Name,Invoice #,Date Issued,Invoice Status,Date Paid,Item Name,Item Description,Rate,Quantity,Line Total,Currency,Project\n"
        "Client Alpha,INV-001,2025-05-01,paid,2025-05-10,Web Design,Homepage Mockup,75.00,10.0,750.00,USD,Website Revamp\n"
        "Client Beta,INV-002,2025-05-03,sent,,Consulting,Strategy Session,150.00,2.0,300.00,USD,Marketing Plan\n"
    )
    fb_filename = os.path.join(test_files_dir, "test_freshbooks_cli.csv")

    try:
        with open(fb_filename, 'w', encoding='utf-8') as f:
            f.write(dummy_freshbooks_content)
        print(f"\n--- Testing FreshBooks CSV Parser (CLI context) ---")
        with open(fb_filename, 'rb') as fb_file_obj:
            freshbooks_bytes_io = io.BytesIO(fb_file_obj.read())
        freshbooks_transactions = parse_freshbooks_csv(
            user_id=test_user_id_cli,
            file_obj=freshbooks_bytes_io,
            filename="test_freshbooks_cli.csv",
            data_context_override="business_test_override",
            project_id_override="FILE_LEVEL_PROJECT_X"
        )
        for tx in freshbooks_transactions:
            print(
                f"Parsed FreshBooks Tx: Client: {tx.client_name}, Amount: {tx.amount}, Status: {tx.invoice_status}, Date Paid: {tx.date_paid}, Desc: {tx.description}, Context: {tx.data_context}, Project: {tx.project_id}")
    except Exception as e_cli:
        print(f"Error parsing FreshBooks test CSV (CLI): {e_cli}", exc_info=True)
    finally:
        if os.path.exists(fb_filename):
            os.remove(fb_filename)

    dummy_chase_content = (
        "Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"
        "DEBIT,05/01/2025,STARBUCKS STORE 123,-5.75,SALE,1000.00,\n"
        "CREDIT,05/03/2025,DIRECT DEPOSIT ACME CORP,1500.00,ACH_CREDIT,2494.25,\n"
    )
    chase_filename = os.path.join(test_files_dir, "test_chase_cli.csv")
    try:
        with open(chase_filename, 'w', encoding='utf-8') as f:
            f.write(dummy_chase_content)
        print(f"\n--- Testing Chase Checking CSV Parser (CLI context) ---")
        with open(chase_filename, 'rb') as chase_file_obj:
            chase_bytes_io = io.BytesIO(chase_file_obj.read())
        chase_transactions = parse_checking_csv(
            user_id=test_user_id_cli,
            file_obj=chase_bytes_io,
            filename="test_chase_cli.csv",
            project_id_override="Personal_Finance_CLI"
        )
        for tx in chase_transactions:
            print(
                f"Parsed Chase Tx: Date: {tx.date}, Desc: {tx.description}, Amount: {tx.amount}, Category: {tx.category}, Context: {tx.data_context}, Project: {tx.project_id}")
    except Exception as e_cli_chase:
        print(f"Error parsing Chase test CSV (CLI): {e_cli_chase}", exc_info=True)
    finally:
        if os.path.exists(chase_filename):
            os.remove(chase_filename)

    if os.path.exists(test_files_dir):
        try:
            os.rmdir(test_files_dir)
        except OSError:
            log.warning(
                f"Could not remove temp test directory {test_files_dir}. It might not be empty or permissions are denied.")
    log.info("Finished parser.py direct execution tests.")


# main.py
import logging
from fastapi import (
    FastAPI, Depends, HTTPException, status, Body,
    UploadFile, File, Form, Query
)
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from typing import List, Optional, Annotated, Dict, Any
import io
import re
import datetime as dt
from dateutil.relativedelta import relativedelta
from dateutil.parser import parse as dateutil_parse, ParserError as DateParserError
from decimal import Decimal

from supabase import create_client, Client
from gotrue.errors import AuthApiError

from config import settings
import database_supabase as db
import parser as csv_parser
import llm_service
import insights
from models_pydantic import (
    UserPydantic, UserCreatePydantic, TokenPydantic,
    TransactionPydantic,
    SummaryPydantic, MonthlyTrendsPydantic, RecurringTransactionsPydantic,
    ClientSummaryDetailPydantic, ClientBreakdownResponsePydantic, UniqueClientResponsePydantic,
    LLMQueryRequest, LLMQueryResponse,
    FeedbackReportPydantic, FeedbackGeneralPydantic
)

# --- App Setup ---
app = FastAPI(title="SpendLens API", version="1.0.0")

# --- Logging Setup ---
log = logging.getLogger("fastapi_app")
log.setLevel(logging.INFO)
if not log.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s:%(funcName)s] - %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)

# --- Supabase Client Initialization ---
supabase_client: Optional[Client] = None
if settings.SUPABASE_URL and settings.SUPABASE_KEY:
    try:
        supabase_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        log.info("Supabase client initialized successfully.")
    except Exception as e:
        log.error(f"Failed to initialize Supabase client: {e}", exc_info=True)
else:
    log.warning("SUPABASE_URL or SUPABASE_KEY is not set. Supabase client not initialized.")

# --- Security & Authentication ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")


# --- Helper: Date Parsing from Query ---
def parse_dates_from_query_str(query: str) -> Optional[Any]:
    q_lower = query.lower();
    today = dt.date.today();
    current_year = today.year
    month_pattern = r'\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b'
    try:
        specific_date_match = re.search(
            r'\b(?:on\s+|date\s+)?(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|' + month_pattern + r'\s+\d{1,2}(?:st|nd|rd|th)?(?:,\s*\d{4})?)\b',
            q_lower)
        if specific_date_match:
            date_str_to_parse = specific_date_match.group(1);
            is_likely_just_month = re.fullmatch(month_pattern, date_str_to_parse.strip())
            if not is_likely_just_month:
                parsed_dt_obj = dateutil_parse(date_str_to_parse, fuzzy=False);
                specific_date = parsed_dt_obj.date()
                if parsed_dt_obj.year >= 1990 and (
                        parsed_dt_obj.year != current_year or str(current_year) in date_str_to_parse or re.search(
                    r'\b\d{1,2}(?:st|nd|rd|th)\b', date_str_to_parse)): return specific_date
    except (DateParserError, ValueError, OverflowError, TypeError, AttributeError):
        pass
    month_this_year_match = re.search(f'({month_pattern})\\s+this\\s+year', q_lower)
    if month_this_year_match:
        month_str = month_this_year_match.group(1)
        try:
            month_dt_obj = dateutil_parse(f"{month_str} 1, {current_year}");
            month = month_dt_obj.month;
            start_date = dt.date(current_year, month, 1)
            end_date = (start_date + relativedelta(months=1)) - dt.timedelta(days=1);
            return start_date, end_date
        except (ValueError, OverflowError):
            pass
    month_year_match = re.search(f'({month_pattern})\\s+(\\d{{4}})', q_lower)
    if month_year_match:
        month_str, year_str = month_year_match.groups();
        year = int(year_str)
        try:
            month_dt_obj = dateutil_parse(f"{month_str} 1, {year}");
            month = month_dt_obj.month;
            start_date = dt.date(year, month, 1)
            end_date = (start_date + relativedelta(months=1)) - dt.timedelta(days=1);
            return start_date, end_date
        except (ValueError, OverflowError):
            pass
    standalone_month_match = re.search(f'({month_pattern})(?!\\s*(?:this\\s+year|\\d))', q_lower)
    if standalone_month_match:
        month_str = standalone_month_match.group(1)
        if not (month_year_match and month_year_match.group(1) == month_str) and not (
                month_this_year_match and month_this_year_match.group(1) == month_str):
            try:
                month_dt_obj = dateutil_parse(f"{month_str} 1, {current_year}");
                month = month_dt_obj.month;
                start_date = dt.date(current_year, month, 1)
                end_date = (start_date + relativedelta(months=1)) - dt.timedelta(days=1);
                return start_date, end_date
            except (ValueError, OverflowError):
                pass
    if "last month" in q_lower: end_of_last_month = today.replace(day=1) - dt.timedelta(
        days=1); return end_of_last_month.replace(day=1), end_of_last_month
    if "this month" in q_lower: return today.replace(day=1), today
    if not month_year_match and not month_this_year_match and not standalone_month_match:
        year_match = re.search(r'\b(in|for|during)\s+(\d{4})\b|\b(\d{4})\b', q_lower)
        if year_match:
            year_str = year_match.group(2) or year_match.group(3)
            try:
                year = int(year_str)
                if 1990 < year <= current_year + 1: return dt.date(year, 1, 1), dt.date(year, 12, 31)
            except ValueError:
                pass
    if "this year" in q_lower and not month_this_year_match and not standalone_month_match: return dt.date(current_year,
                                                                                                           1,
                                                                                                           1), dt.date(
        current_year, 12, 31)
    if "last year" in q_lower: year = current_year - 1; return dt.date(year, 1, 1), dt.date(year, 12, 31)
    return None


# --- Authentication Dependencies ---
async def get_current_supabase_user(token: Annotated[str, Depends(oauth2_scheme)]) -> db.User:
    if not supabase_client: raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                                detail="Auth service unavailable")
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                          detail="Could not validate credentials",
                                          headers={"WWW-Authenticate": "Bearer"})
    try:
        auth_response = supabase_client.auth.get_user(token);
        supabase_user = auth_response.user
        if not supabase_user or not supabase_user.id or not supabase_user.email: raise credentials_exception
        app_user_profile = db.get_user_profile_by_id(str(supabase_user.id))
        if not app_user_profile:
            app_user_profile = db.create_user_profile(str(supabase_user.id), supabase_user.email)
            if not app_user_profile: raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                                         detail="User profile missing/could not be created.")
        return app_user_profile
    except AuthApiError as e:
        log.warning(f"Supabase AuthApiError during get_current_user: {e.message}"); raise credentials_exception
    except Exception:
        log.error("Unexpected error in get_current_supabase_user", exc_info=True); raise credentials_exception


# --- API Endpoints ---
@app.get("/")
async def root(): return {"message": "Welcome to SpendLens API"}


# --- Auth Endpoints ---
@app.post("/auth/register", response_model=UserPydantic, status_code=status.HTTP_201_CREATED)
async def register_user_endpoint(user_in: UserCreatePydantic):
    if not supabase_client: raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                                detail="Auth service unavailable")
    try:
        auth_response = supabase_client.auth.sign_up({"email": user_in.email, "password": user_in.password})
        if auth_response.user and auth_response.user.id and auth_response.user.email:
            profile = db.create_user_profile(str(auth_response.user.id), auth_response.user.email)
            if not profile: profile = db.get_user_profile_by_id(str(auth_response.user.id))
            if not profile: raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                                detail="User registered but profile could not be confirmed.")
            return UserPydantic(id=str(auth_response.user.id), email=auth_response.user.email,
                                username=profile.username)
        elif auth_response.error:
            if "already registered" in auth_response.error.message.lower(): raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Email already registered.")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=auth_response.error.message)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Registration error without specific message from Supabase.")
    except AuthApiError as e:
        if "user already registered" in e.message.lower(): raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                                                               detail="Email already registered.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)
    except Exception as e:
        log.error(f"Unexpected exception during registration for {user_in.email}: {e}",
                  exc_info=True); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                                      detail="Internal error during registration.")


@app.post("/auth/token", response_model=TokenPydantic)
async def login_for_access_token_endpoint(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    if not supabase_client: raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                                detail="Auth service unavailable")
    user_email = form_data.username
    try:
        auth_response = supabase_client.auth.sign_in_with_password(
            {"email": user_email, "password": form_data.password})
        if auth_response.user and auth_response.session and auth_response.session.access_token:
            supa_user = auth_response.user;
            profile = db.get_user_profile_by_id(str(supa_user.id))
            if not profile: profile = db.create_user_profile(str(supa_user.id), supa_user.email or user_email)
            user_for_token = UserPydantic(id=str(supa_user.id), email=supa_user.email or "N/A",
                                          username=profile.username if profile else None)
            return TokenPydantic(access_token=auth_response.session.access_token, token_type="bearer",
                                 refresh_token=auth_response.session.refresh_token, user=user_for_token)
        elif auth_response.error:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Login error with unexpected response structure.")
    except AuthApiError as e:
        if "invalid login credentials" in e.message.lower():
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid login credentials.")
        elif "email not confirmed" in e.message.lower():
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Email not confirmed. Please check your inbox.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)
    except Exception as e:
        log.error(f"Unexpected exception during login for {user_email}: {e}", exc_info=True); raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal login error.")


@app.get("/users/me", response_model=UserPydantic)
async def read_users_me_endpoint(
        current_user: Annotated[db.User, Depends(get_current_supabase_user)]): return UserPydantic(id=current_user.id,
                                                                                                   email=current_user.email,
                                                                                                   username=current_user.username)


# --- File Upload Endpoint ---
@app.post("/upload/transactions")
async def upload_transaction_files(
        current_user: Annotated[db.User, Depends(get_current_supabase_user)],
        checking_file: Optional[UploadFile] = File(None, description="Chase Checking CSV file"),
        credit_file: Optional[UploadFile] = File(None, description="Chase Credit CSV file"),
        stripe_file: Optional[UploadFile] = File(None, description="Stripe Payouts CSV file"),
        paypal_file: Optional[UploadFile] = File(None, description="PayPal Transactions CSV file"),
        invoice_file: Optional[UploadFile] = File(None, description="Generic Invoices CSV file"),
        clockify_file: Optional[UploadFile] = File(None, description="Clockify Time Log CSV file"),
        toggl_file: Optional[UploadFile] = File(None, description="Toggl Time Log CSV file")
):
    user_id_str = current_user.id;
    log.info(f"User {user_id_str}: File upload started.")
    parser_map = {
        "checking_file": csv_parser.parse_checking_csv, "credit_file": csv_parser.parse_credit_csv,
        "stripe_file": csv_parser.parse_stripe_csv, "paypal_file": csv_parser.parse_paypal_csv,
        "invoice_file": csv_parser.parse_invoice_csv, "clockify_file": csv_parser.parse_clockify_csv,
        "toggl_file": csv_parser.parse_toggl_csv,
    }
    uploaded_files_dict = {
        "checking_file": checking_file, "credit_file": credit_file, "stripe_file": stripe_file,
        "paypal_file": paypal_file, "invoice_file": invoice_file, "clockify_file": clockify_file,
        "toggl_file": toggl_file
    }
    files_processed_names, all_transactions, errors, processed_any_file = [], [], [], False
    try:
        db.clear_transactions_for_user(user_id_str); db.clear_llm_rules_for_user(user_id_str)
    except Exception as e:
        log.error(f"User {user_id_str}: Error clearing data: {e}", exc_info=True); raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to prepare for upload.")

    for file_key, file_obj in uploaded_files_dict.items():
        if file_obj and file_obj.filename:
            processed_any_file = True;
            original_filename = file_obj.filename;
            parser_function = parser_map.get(file_key)
            if not parser_function: errors.append(f"No parser for '{original_filename}' (key: {file_key})."); continue
            if not csv_parser.allowed_file(original_filename): errors.append(
                f"File type not allowed for '{original_filename}'."); continue
            log.info(f"User {user_id_str}: Processing '{original_filename}' with parser for '{file_key}'.")
            file_stream = None
            try:
                content = await file_obj.read();
                file_stream = io.BytesIO(content)
                txns = parser_function(user_id=user_id_str, file_obj=file_stream, filename=original_filename)
                all_transactions.extend(txns);
                files_processed_names.append(original_filename)
                log.info(f"User {user_id_str}: Parsed {len(txns)} txns from '{original_filename}'.")
            except (ValueError, RuntimeError) as pe:
                log.error(f"User {user_id_str}: Parsing error for '{original_filename}': {pe}",
                          exc_info=True); errors.append(f"Error processing '{original_filename}': {str(pe)}")
            except Exception as e:
                log.error(f"User {user_id_str}: Unexpected error with '{original_filename}': {e}",
                          exc_info=True); errors.append(f"Unexpected error with '{original_filename}'.")
            finally:
                if file_obj: await file_obj.close()
                if file_stream: file_stream.close()

    if not processed_any_file and not errors: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                                                  detail="No files uploaded or recognized.")
    if not processed_any_file and errors: return JSONResponse(
        content={"message": "File processing failed.", "errors": errors}, status_code=status.HTTP_400_BAD_REQUEST)

    saved_count = 0
    if all_transactions:
        try:
            saved_count = db.save_transactions(user_id_str, all_transactions)
        except Exception as e:
            log.error(f"User {user_id_str}: Database save error: {e}", exc_info=True); errors.append(
                "Database save error.")

    llm_suggestions_count = 0
    if saved_count > 0:
        try:
            uncategorized_tx = [tx for tx in all_transactions if tx.category == 'Uncategorized']
            if uncategorized_tx:
                valid_categories = [
                    "Revenue - Product Sales", "Revenue - Service Fees", "Revenue - Client Project",
                    "Software Subscription", "Contractor Payment", "Office Supplies", "Travel Expense",
                    "Meals & Entertainment", "Utilities", "Rent/Lease", "Advertising & Marketing",
                    "Professional Fees (Legal, Accounting)", "Bank Fees", "Hardware Purchase",
                    "Shipping & Postage", "Salaries & Wages", "Payroll Taxes", "Income Tax Payment",
                    "Insurance (Business)", "Client Refund", "Payout Processing Fee", "Platform Fee",
                    "Loan Payment", "Interest Expense", "Owner Draw/Distribution", "Capital Investment",
                    "Time Tracking Revenue", "Non-billable Time",
                    "Other Income", "Other Expense", "Ignore", "Uncategorized"
                ]
                context_rules = db.get_user_rules(user_id_str)
                suggested_map = llm_service.suggest_categories_for_transactions(uncategorized_tx, valid_categories,
                                                                                context_rules)
                if suggested_map:
                    for desc_key, cat in suggested_map.items():
                        db.save_llm_rule(user_id_str, desc_key, cat)
                        llm_suggestions_count += 1
        except Exception as llm_e:
            log.error(f"User {user_id_str}: LLM suggestion error: {llm_e}", exc_info=True); errors.append(
                f"AI Suggestion Error: {str(llm_e)}")

    final_message = f"Processed {saved_count} txns from {len(files_processed_names)} file(s)."
    if llm_suggestions_count > 0: final_message += f" Saved {llm_suggestions_count} AI suggestions."
    response_data = {"message": final_message, "files_processed": files_processed_names,
                     "transactions_saved_count": saved_count, "ai_suggestions_count": llm_suggestions_count}
    if errors:
        response_data["errors"] = errors
        status_code_resp = status.HTTP_207_MULTI_STATUS if files_processed_names and saved_count > 0 else status.HTTP_400_BAD_REQUEST
        if not saved_count and any(
            "database" in e.lower() for e in errors): status_code_resp = status.HTTP_500_INTERNAL_SERVER_ERROR
        return JSONResponse(content=response_data, status_code=status_code_resp)
    return response_data


# --- Transaction Endpoints ---
@app.get("/transactions", response_model=List[TransactionPydantic])
async def get_transactions_endpoint(current_user: Annotated[db.User, Depends(get_current_supabase_user)],
                                    start_date: Optional[dt.date] = None, end_date: Optional[dt.date] = None,
                                    category: Optional[str] = None, transaction_origin: Optional[str] = None,
                                    client_name: Optional[str] = None):
    return db.get_all_transactions(user_id=current_user.id, start_date=start_date, end_date=end_date, category=category,
                                   transaction_origin=transaction_origin, client_name=client_name)


@app.put("/transactions/{transaction_id}/category", response_model=TransactionPydantic)
async def update_transaction_category_endpoint(
        transaction_id: int,
        current_user: Annotated[db.User, Depends(get_current_supabase_user)],
        payload: Dict[str, str] = Body(...)
):
    user_id_str = current_user.id
    new_category = payload.get("category")
    if not new_category:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing 'category' in request body.")

    log.info(f"User {user_id_str}: Updating category for TxID {transaction_id} to '{new_category}'.")
    tx_to_update = db.get_transaction_by_id_for_user(user_id_str, transaction_id)
    if not tx_to_update:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found.")

    success = db.update_transaction_category(user_id_str, transaction_id, new_category)
    if not success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update category.")

    desc_for_rule = tx_to_update.raw_description or tx_to_update.description
    if desc_for_rule:
        try:
            csv_parser.add_user_rule(user_id_str, desc_for_rule, new_category)
            log.info(f"User {user_id_str}: Saved user rule for '{desc_for_rule}' -> '{new_category}'.")
        except Exception as rule_save_err:
            log.error(f"User {user_id_str}: Failed to save user rule for Tx {transaction_id}: {rule_save_err}",
                      exc_info=True)  # Added exc_info

    updated_tx = db.get_transaction_by_id_for_user(user_id_str, transaction_id)
    if not updated_tx:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to retrieve updated transaction.")
    return updated_tx


# --- Insights Endpoints ---
@app.get("/insights/summary", response_model=SummaryPydantic)
async def get_summary_insights_endpoint(current_user: Annotated[db.User, Depends(get_current_supabase_user)],
                                        start_date: Optional[dt.date] = None, end_date: Optional[dt.date] = None):
    transactions_db = db.get_all_transactions(current_user.id, start_date, end_date)
    summary_data_dict = insights.calculate_summary_insights(transactions_db)
    try:
        for key in ['total_income', 'total_spending', 'total_payments_transfers', 'net_flow_operational',
                    'net_change_total', 'average_transaction_amount', 'median_transaction_amount']:
            if key in summary_data_dict and isinstance(summary_data_dict[key], Decimal): summary_data_dict[key] = str(
                summary_data_dict[key])
        for cat_dict_key in ['spending_by_category', 'income_by_category']:
            if cat_dict_key in summary_data_dict and isinstance(summary_data_dict[cat_dict_key], dict):
                summary_data_dict[cat_dict_key] = {k: str(v) if isinstance(v, Decimal) else v for k, v in
                                                   summary_data_dict[cat_dict_key].items()}
        return SummaryPydantic(**summary_data_dict)
    except Exception as e:
        log.error(f"Error converting summary: {e}. Data: {summary_data_dict}", exc_info=True); raise HTTPException(
            status_code=500, detail="Error processing summary.")


@app.get("/insights/trends/monthly", response_model=MonthlyTrendsPydantic)
async def get_monthly_trends_endpoint(current_user: Annotated[db.User, Depends(get_current_supabase_user)],
                                      start_date: Optional[dt.date] = None, end_date: Optional[dt.date] = None):
    transactions_db = db.get_all_transactions(current_user.id, start_date, end_date)
    trends_data_dict = insights.calculate_monthly_spending_trends(transactions=transactions_db)
    try:
        return MonthlyTrendsPydantic(**trends_data_dict)
    except Exception as e:
        log.error(f"Error converting trends: {e}. Data: {trends_data_dict}", exc_info=True); raise HTTPException(
            status_code=500, detail="Error processing trends.")


@app.get("/insights/recurring", response_model=RecurringTransactionsPydantic)
async def get_recurring_transactions_endpoint(current_user: Annotated[db.User, Depends(get_current_supabase_user)],
                                              min_occurrences: int = Query(3, ge=2),
                                              days_tolerance: int = Query(7, ge=1),
                                              amount_tolerance_percent: float = Query(15.0, ge=0.0, le=100.0)):
    all_transactions_db = db.get_all_transactions(current_user.id)
    if not all_transactions_db: return RecurringTransactionsPydantic(recurring_groups=[])
    recurring_data_dict = insights.identify_recurring_transactions(transactions=all_transactions_db,
                                                                   min_occurrences=min_occurrences,
                                                                   days_tolerance=days_tolerance,
                                                                   amount_tolerance_percent=amount_tolerance_percent)
    try:
        return RecurringTransactionsPydantic(**recurring_data_dict)
    except Exception as e:
        log.error(f"Error converting recurring: {e}. Data: {recurring_data_dict}", exc_info=True); raise HTTPException(
            status_code=500, detail="Error processing recurring.")


# --- Client Breakdown Endpoints ---
@app.get("/clients", response_model=UniqueClientResponsePydantic)
async def get_unique_clients_endpoint(current_user: Annotated[db.User, Depends(get_current_supabase_user)],
                                      start_date: Optional[dt.date] = None, end_date: Optional[dt.date] = None):
    client_names = db.get_unique_client_names(user_id=current_user.id, start_date=start_date, end_date=end_date)
    return UniqueClientResponsePydantic(clients=client_names)


@app.get("/insights/client_breakdown", response_model=ClientBreakdownResponsePydantic)
async def get_client_breakdown_endpoint(current_user: Annotated[db.User, Depends(get_current_supabase_user)],
                                        start_date: Optional[dt.date] = None, end_date: Optional[dt.date] = None):
    client_summaries_db = db.calculate_summary_by_client(user_id=current_user.id, start_date=start_date,
                                                         end_date=end_date)
    response_data: Dict[str, Any] = {}
    for client_name, summary_details in client_summaries_db.items():
        response_data[client_name] = ClientSummaryDetailPydantic(
            total_revenue=str(summary_details.get("total_revenue", Decimal(0)).quantize(Decimal("0.01"))),
            total_direct_cost=str(summary_details.get("total_direct_cost", Decimal(0)).quantize(Decimal("0.01"))),
            net_from_client=str(summary_details.get("net_from_client", Decimal(0)).quantize(Decimal("0.01")))
        )
    return response_data


# --- AI Assistant & Feedback Endpoints ---
@app.post("/ai/query/financial", response_model=LLMQueryResponse)
async def query_financial_assistant_endpoint(current_user: Annotated[db.User, Depends(get_current_supabase_user)],
                                             request_body: LLMQueryRequest):
    user_id_str, question = current_user.id, request_body.query;
    today = dt.date.today()
    default_context_days = settings.DEFAULT_LLM_CONTEXT_DAYS
    context_start_date, context_end_date = today - dt.timedelta(days=default_context_days), today
    parsed_query_dates = parse_dates_from_query_str(question)
    query_specific_start, query_specific_end = None, None
    if isinstance(parsed_query_dates, dt.date):
        query_specific_start, query_specific_end = parsed_query_dates, parsed_query_dates
    elif isinstance(parsed_query_dates, tuple):
        query_specific_start, query_specific_end = parsed_query_dates
    fetch_start, fetch_end = query_specific_start or context_start_date, query_specific_end or context_end_date
    transactions_for_llm = db.get_all_transactions(user_id_str, fetch_start, fetch_end)
    summary_data_for_llm = insights.calculate_summary_insights(transactions_for_llm) if transactions_for_llm else None
    llm_answer_text, llm_status = llm_service.answer_financial_question(question=question,
                                                                        transactions=transactions_for_llm,
                                                                        summary_data=summary_data_for_llm,
                                                                        start_date_str=fetch_start.isoformat() if fetch_start else None,
                                                                        end_date_str=fetch_end.isoformat() if fetch_end else None,
                                                                        pre_calculated_result=None)
    if llm_status != 'success': db.log_llm_failed_query(user_id_str, question, llm_answer_text, llm_status)
    if llm_status == 'blocked': raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                                    detail=f"Query blocked: {llm_answer_text}")
    return LLMQueryResponse(question=question, answer=llm_answer_text, status=llm_status)


@app.post("/feedback/report_error", status_code=status.HTTP_201_CREATED)
async def report_llm_error_endpoint(current_user: Annotated[db.User, Depends(get_current_supabase_user)],
                                    report: FeedbackReportPydantic):
    db.log_llm_user_report(current_user.id, report.query, report.incorrect_response, report.user_comment)
    return {"message": "Error report submitted successfully."}


@app.post("/feedback/submit_general", status_code=status.HTTP_201_CREATED)
async def submit_general_feedback_endpoint(feedback: FeedbackGeneralPydantic, current_user: Annotated[
    Optional[db.User], Depends(get_current_supabase_user)] = None):
    user_id_str = current_user.id if current_user else None
    db.log_user_feedback(user_id_str, feedback.feedback_type, feedback.comment, feedback.contact_email)
    return {"message": "Feedback submitted successfully."}


if __name__ == "__main__":
    import uvicorn

    log.info(f"Starting Uvicorn server for SpendLens API on port {settings.FASTAPI_PORT}...")
    uvicorn.run("main:app", host=settings.FASTAPI_HOST, port=settings.FASTAPI_PORT, reload=True)

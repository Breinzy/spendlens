# routers/transactions_router.py (Rebuild Step 4 - Update Category Logic)
import logging
import io
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query, Body
import datetime as dt

# Imports
from config import settings
from models_pydantic import TransactionPydantic, UserPydantic, CategoryUpdatePydantic  # Added CategoryUpdatePydantic
import database_supabase as db_supabase
import parser
from auth.dependencies import get_current_supabase_user

log = logging.getLogger('transactions_router')
if not log.handlers and not (hasattr(log.parent, 'handlers') and log.parent.handlers):
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s:%(funcName)s] - %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)
    log.propagate = False

router = APIRouter(
    prefix="/api/v1/transactions",
    tags=["Transactions"],
    dependencies=[Depends(get_current_supabase_user)],
    responses={404: {"description": "Not found"}},
)
log.info("transactions_router.router object defined successfully (Rebuild Step 4).")


@router.post("/upload/csv", summary="Upload and process a CSV transaction file")
async def upload_csv_transactions(
        file: UploadFile = File(..., description="The CSV file to upload."),
        file_type: str = Form(..., description="Type of the CSV file (e.g., 'freshbooks', 'chase_checking')."),
        current_user: UserPydantic = Depends(get_current_supabase_user)
):
    # --- Logic from Rebuild Step 2 - Confirmed Working ---
    user_id = current_user.id
    log.info(f"User {user_id}: API Upload request for file '{file.filename}', type '{file_type}'.")
    if not file.filename: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No file name provided.")
    if not hasattr(parser, 'allowed_file'):
        log.warning("parser.py does not have an 'allowed_file' function. Performing basic extension check.")
        filename_ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ""
        if filename_ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="File type not allowed (basic check). Please upload a CSV.")
    elif not parser.allowed_file(file.filename, settings.ALLOWED_EXTENSIONS):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="File type not allowed. Please upload a CSV.")
    contents = await file.read();
    file_stream = io.BytesIO(contents)
    parser_function_map = {
        "chase_checking": parser.parse_checking_csv, "chase_credit": parser.parse_credit_csv,
        "stripe": parser.parse_stripe_csv, "paypal": parser.parse_paypal_csv,
        "invoice": parser.parse_invoice_csv, "freshbooks": parser.parse_freshbooks_csv,
        "clockify": parser.parse_clockify_csv, "toggl": parser.parse_toggl_csv,
    }
    selected_parser_func = parser_function_map.get(file_type)
    if not selected_parser_func:
        file_stream.close();
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported file type: {file_type}")
    try:
        parsed_transactions = selected_parser_func(user_id=user_id, file_obj=file_stream, filename=file.filename)
        saved_count = 0
        if parsed_transactions:
            saved_count = db_supabase.save_transactions(user_id, parsed_transactions)
            log.info(f"User {user_id}: Saved {saved_count} transactions to database for file '{file.filename}'.")
        else:
            log.info(f"User {user_id}: No transactions parsed from '{file.filename}' to save.")
        return {"filename": file.filename, "file_type": file_type, "transactions_parsed": len(parsed_transactions),
                "transactions_saved": saved_count, "message": "File processed successfully."}
    except ValueError as ve:
        log.error(f"User {user_id}: Parsing ValueError for '{file.filename}': {ve}");
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"Error processing file '{file.filename}': {str(ve)}")
    except RuntimeError as rte:
        log.error(f"User {user_id}: Parser RuntimeError for '{file.filename}': {rte}");
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Critical error processing file '{file.filename}'.")
    except Exception as e:
        log.error(f"User {user_id}: Unexpected error processing file '{file.filename}': {e}", exc_info=True);
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"An unexpected error occurred with file '{file.filename}'.")
    finally:
        if file_stream: file_stream.close()


@router.get("", response_model=List[TransactionPydantic], summary="Get transactions for the current user")
async def get_transactions(
        current_user: UserPydantic = Depends(get_current_supabase_user),
        start_date: Optional[dt.date] = Query(None, description="Filter by start date (YYYY-MM-DD)"),
        end_date: Optional[dt.date] = Query(None, description="Filter by end date (YYYY-MM-DD)"),
        category: Optional[str] = Query(None, description="Filter by category"),
        transaction_origin: Optional[str] = Query(None,
                                                  description="Filter by transaction origin (e.g., 'freshbooks_invoice')"),
        client_name: Optional[str] = Query(None, description="Filter by client name")
):
    # --- Logic from Rebuild Step 3 - Confirmed Working ---
    user_id = current_user.id
    log.info(
        f"User {user_id}: Fetching transactions with filters: start={start_date}, end={end_date}, cat={category}, origin={transaction_origin}, client={client_name}")
    if start_date and end_date and start_date > end_date: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                                                              detail="Start date cannot be after end date.")
    try:
        db_transactions = db_supabase.get_all_transactions(user_id=user_id, start_date=start_date, end_date=end_date,
                                                           category=category, transaction_origin=transaction_origin,
                                                           client_name=client_name)
        pydantic_transactions = [TransactionPydantic.model_validate(tx.to_dict() if hasattr(tx, 'to_dict') else tx) for
                                 tx in db_transactions]
        log.info(f"User {user_id}: Returning {len(pydantic_transactions)} transactions.")
        return pydantic_transactions
    except Exception as e:
        log.error(f"User {user_id}: Error fetching transactions: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to retrieve transactions.")


@router.put("/{transaction_id}/category", response_model=TransactionPydantic,
            summary="Update category for a specific transaction")
async def update_transaction_category_api(
        transaction_id: int,
        payload: CategoryUpdatePydantic,  # Use the Pydantic model for request body validation
        current_user: UserPydantic = Depends(get_current_supabase_user)
):
    user_id = current_user.id
    new_category = payload.new_category  # Access via Pydantic model attribute
    log.info(f"User {user_id}: Request to update category for Tx ID {transaction_id} to '{new_category}'.")

    tx_to_update = db_supabase.get_transaction_by_id_for_user(user_id, transaction_id)
    if not tx_to_update:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found or access denied.")

    # Proceed with update
    try:
        success = db_supabase.update_transaction_category(user_id, transaction_id, new_category)
        if not success:
            # This case might occur if the row was deleted between the check and the update,
            # or if user_id check inside update_transaction_category failed (though get_transaction_by_id_for_user should prevent this).
            log.error(f"User {user_id}: DB update_transaction_category returned False for Tx ID {transaction_id}.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail="Failed to update transaction category in database.")

        # Optionally, save this as a user rule if the update was successful
        # Use the raw_description from the fetched transaction for the rule
        desc_for_rule = tx_to_update.raw_description or tx_to_update.description
        if desc_for_rule:
            try:
                # Assuming db_supabase.save_user_rule is the correct function to call
                db_supabase.save_user_rule(user_id, desc_for_rule, new_category)
                log.info(f"User {user_id}: Saved user rule for desc '{desc_for_rule}' -> '{new_category}'.")
            except Exception as rule_save_err:
                # Log this error but don't fail the entire request, as category update was successful
                log.error(
                    f"User {user_id}: Failed to save user rule for Tx {transaction_id} after category update: {rule_save_err}")

        # Fetch the updated transaction to return it
        updated_tx = db_supabase.get_transaction_by_id_for_user(user_id, transaction_id)
        if not updated_tx:
            log.error(
                f"User {user_id}: Failed to retrieve Tx ID {transaction_id} after supposedly successful category update.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail="Failed to retrieve updated transaction.")

        return TransactionPydantic.model_validate(
            updated_tx.to_dict() if hasattr(updated_tx, 'to_dict') else updated_tx)

    except Exception as e:
        log.error(f"User {user_id}: Unexpected error updating category for Tx ID {transaction_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="An unexpected error occurred while updating category.")


print("transactions_router.py (Rebuild Step 4) loaded. Router object should be defined.")
if 'router' in globals() and router is not None:
    print("transactions_router.router IS defined in Rebuild Step 4.")
else:
    print(
        "transactions_router.router IS NOT defined in Rebuild Step 4 (APIRouter instantiation likely failed or name mismatch).")

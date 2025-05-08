# routers/transactions_router.py
import logging
import io
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query

import datetime as dt

# Project specific imports
from config import settings
from models_pydantic import TransactionPydantic, UserPydantic, CategoryUpdatePydantic
import database_supabase as db_supabase
import parser as csv_parser # Renamed to avoid conflict with 'parser' variable name if any
from auth.dependencies import get_current_supabase_user

# Configure logging for this router
log = logging.getLogger('transactions_router')
if not log.handlers and not (hasattr(log.parent, 'handlers') and log.parent.handlers): # Avoid duplicate handlers
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s:%(module)s:%(funcName)s:%(lineno)d] - %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)
    log.propagate = False # Prevent passing to root logger if it has handlers

router = APIRouter(
    prefix="/api/v1/transactions",
    tags=["Transactions"],
    dependencies=[Depends(get_current_supabase_user)], # Secure all routes in this router
    responses={404: {"description": "Not found"}},
)
log.info("transactions_router.router object defined successfully.")

@router.post("/upload/csv", summary="Upload and process a CSV transaction file")
async def upload_csv_transactions(
        current_user: UserPydantic = Depends(get_current_supabase_user),
        file: UploadFile = File(..., description="The CSV file to upload."),
        file_type: str = Form(..., description="Type of the CSV file (e.g., 'freshbooks', 'chase_checking')."),
        project_id: Optional[str] = Form(None, description="Optional project ID to associate with these transactions.")
):
    """
    Handles CSV file uploads, parses them based on file_type,
    and saves transactions to the database.
    For V2, all uploaded data is automatically assigned data_context='business'.
    An optional project_id can be provided for the entire file.
    """
    user_id = current_user.id
    data_context_for_v2 = "business" # For V2, all uploads are business context

    log.info(f"User {user_id}: API Upload request for file '{file.filename}', type '{file_type}', project ID: '{project_id}', context: '{data_context_for_v2}'.")

    if not file.filename:
        log.warning(f"User {user_id}: Upload attempt with no filename.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No file name provided.")

    # File extension check (using the parser's utility function)
    if not csv_parser.allowed_file(file.filename, settings.ALLOWED_EXTENSIONS):
        log.warning(f"User {user_id}: File type not allowed for '{file.filename}'. Allowed: {settings.ALLOWED_EXTENSIONS}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"File type not allowed for '{file.filename}'. Please upload a CSV.")

    file_stream = None # Initialize to ensure it's defined for finally block
    try:
        contents = await file.read()
        file_stream = io.BytesIO(contents) # Keep as BytesIO, parser will handle TextIOWrapper

        # Map file_type to the correct parser function from csv_parser module
        parser_function_map = {
            "chase_checking": csv_parser.parse_checking_csv,
            "chase_credit": csv_parser.parse_credit_csv,
            "stripe": csv_parser.parse_stripe_csv,
            "paypal": csv_parser.parse_paypal_csv,
            "invoice": csv_parser.parse_invoice_csv, # Generic invoice
            "freshbooks": csv_parser.parse_freshbooks_csv,
            "clockify": csv_parser.parse_clockify_csv,
            "toggl": csv_parser.parse_toggl_csv,
        }
        selected_parser_func = parser_function_map.get(file_type)

        if not selected_parser_func:
            log.warning(f"User {user_id}: Unsupported file type '{file_type}' for file '{file.filename}'.")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported file type: {file_type}")

        # Call the parser function
        # The parser function itself will now handle setting data_context and using project_id
        parsed_transactions = selected_parser_func(
            user_id=user_id,
            file_obj=file_stream, # Pass BytesIO
            filename=file.filename,
            # Pass data_context and project_id to the parser,
            # which will then pass it to parse_csv_with_schema
            data_context_override=data_context_for_v2,
            project_id_override=project_id
        )
        log.info(f"User {user_id}: Parsed {len(parsed_transactions)} transactions from '{file.filename}'.")

        saved_count = 0
        if parsed_transactions:
            # The save_transactions function in db_supabase now handles data_context from Transaction objects
            saved_count = db_supabase.save_transactions(user_id, parsed_transactions)
            log.info(f"User {user_id}: Saved {saved_count} transactions to database for file '{file.filename}'.")
        else:
            log.info(f"User {user_id}: No transactions parsed from '{file.filename}' to save.")

        return {
            "filename": file.filename,
            "file_type": file_type,
            "project_id": project_id,
            "data_context_assigned": data_context_for_v2,
            "transactions_parsed": len(parsed_transactions),
            "transactions_saved": saved_count,
            "message": "File processed successfully."
        }

    except ValueError as ve: # Specific errors from parser (e.g., missing columns)
        log.error(f"User {user_id}: Parsing ValueError for '{file.filename}': {ve}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"Error processing file '{file.filename}': {str(ve)}")
    except RuntimeError as rte: # Critical errors from parser
        log.error(f"User {user_id}: Parser RuntimeError for '{file.filename}': {rte}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Critical error processing file '{file.filename}'.")
    except HTTPException: # Re-raise HTTPExceptions directly
        raise
    except Exception as e: # Catch-all for other unexpected errors
        log.error(f"User {user_id}: Unexpected error processing file '{file.filename}': {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"An unexpected error occurred with file '{file.filename}'.")
    finally:
        if file_stream:
            file_stream.close()
        if file: # Ensure the UploadFile object is closed
            await file.close()


@router.get("", response_model=List[TransactionPydantic], summary="Get transactions for the current user")
async def get_transactions(
        current_user: UserPydantic = Depends(get_current_supabase_user),
        start_date: Optional[dt.date] = Query(None, description="Filter by start date (YYYY-MM-DD)"),
        end_date: Optional[dt.date] = Query(None, description="Filter by end date (YYYY-MM-DD)"),
        category: Optional[str] = Query(None, description="Filter by category"),
        transaction_origin: Optional[str] = Query(None, description="Filter by transaction origin (e.g., 'freshbooks_invoice')"),
        client_name: Optional[str] = Query(None, description="Filter by client name (case-insensitive, partial match)"),
        data_context: Optional[str] = Query("business", description="Filter by data context. Defaults to 'business' for V2."), # NEW, defaults to business
        project_id: Optional[str] = Query(None, description="Filter by project ID.") # NEW
):
    user_id = current_user.id
    log.info(
        f"User {user_id}: Fetching transactions with filters: start={start_date}, end={end_date}, cat={category}, origin={transaction_origin}, client={client_name}, context={data_context}, project={project_id}")

    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Start date cannot be after end date.")

    try:
        # Pass the new filters to the database function
        db_transactions = db_supabase.get_all_transactions(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            category=category,
            transaction_origin=transaction_origin,
            client_name=client_name,
            data_context=data_context, # Pass data_context
            project_id=project_id      # Pass project_id
        )

        # Convert DB models to Pydantic models for the response
        # Ensure Transaction.to_dict() and TransactionPydantic include data_context
        pydantic_transactions = [TransactionPydantic.model_validate(tx.to_dict() if hasattr(tx, 'to_dict') else tx) for tx in db_transactions]
        log.info(f"User {user_id}: Returning {len(pydantic_transactions)} transactions based on filters.")
        return pydantic_transactions
    except Exception as e:
        log.error(f"User {user_id}: Error fetching transactions: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to retrieve transactions.")


@router.put("/{transaction_id}/category", response_model=TransactionPydantic, summary="Update category for a specific transaction")
async def update_transaction_category_api(
        transaction_id: int,
        payload: CategoryUpdatePydantic, # Use Pydantic model for request body
        current_user: UserPydantic = Depends(get_current_supabase_user)
):
    user_id = current_user.id
    new_category = payload.new_category
    log.info(f"User {user_id}: Request to update category for Tx ID {transaction_id} to '{new_category}'.")

    # Verify transaction exists and belongs to the user
    tx_to_update = db_supabase.get_transaction_by_id_for_user(user_id, transaction_id)
    if not tx_to_update:
        log.warning(f"User {user_id}: Attempt to update category for non-existent or unauthorized Tx ID {transaction_id}.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found or access denied.")

    try:
        success = db_supabase.update_transaction_category(user_id, transaction_id, new_category)
        if not success:
            # This might happen if the row was deleted between the check and update,
            # or if the user_id check within update_transaction_category failed (though less likely).
            log.error(f"User {user_id}: DB update_transaction_category returned False for Tx ID {transaction_id}.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail="Failed to update transaction category in database.")

        # Save this manual categorization as a user rule
        # Use raw_description if available, otherwise fallback to description
        desc_for_rule = tx_to_update.raw_description or tx_to_update.description
        if desc_for_rule:
            try:
                # Assuming csv_parser.add_user_rule is the correct function (from parser.py)
                csv_parser.add_user_rule(user_id, desc_for_rule, new_category)
                log.info(f"User {user_id}: Saved user rule for desc '{desc_for_rule}' -> '{new_category}'.")
            except Exception as rule_save_err:
                # Log error but don't fail the request, as category update was successful
                log.error(f"User {user_id}: Failed to save user rule for Tx {transaction_id} after category update: {rule_save_err}", exc_info=True)

        # Fetch the updated transaction to return it
        updated_tx_db = db_supabase.get_transaction_by_id_for_user(user_id, transaction_id)
        if not updated_tx_db: # Should not happen if update was successful
            log.error(f"User {user_id}: Failed to retrieve Tx ID {transaction_id} after supposedly successful category update.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail="Failed to retrieve updated transaction.")

        return TransactionPydantic.model_validate(updated_tx_db.to_dict() if hasattr(updated_tx_db, 'to_dict') else updated_tx_db)

    except HTTPException: # Re-raise HTTPExceptions
        raise
    except Exception as e:
        log.error(f"User {user_id}: Unexpected error updating category for Tx ID {transaction_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="An unexpected error occurred while updating category.")

log.info("transactions_router.py loaded and router object should be accessible.")

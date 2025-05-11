# routers/insights_router.py
import logging
import datetime as dt
from typing import Optional, List
from dateutil.relativedelta import relativedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status

# Project specific imports
from models_pydantic import (
    UserPydantic,
    FullInsightsReportPydantic,
    MonthlyRevenueTrendResponsePydantic,
    LLMQueryRequest,  # For AI query
    LLMQueryResponse  # For AI response
)
import database_supabase as db_supabase
import insights
import llm_service  # Import the LLM service
from auth.dependencies import get_current_supabase_user
from config import settings  # For default LLM context days

router = APIRouter(
    tags=["Insights"],
    dependencies=[Depends(get_current_supabase_user)],
    responses={404: {"description": "Not found"}},
)

log = logging.getLogger('insights_router')
if not log.handlers and not (hasattr(log.parent, 'handlers') and log.parent.handlers):
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s:%(funcName)s] - %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)
    log.propagate = False


@router.get("/insights/summary", response_model=FullInsightsReportPydantic,
            summary="Get comprehensive financial insights for the current user")
async def get_full_financial_summary(
        current_user: UserPydantic = Depends(get_current_supabase_user),
        start_date: Optional[dt.date] = Query(None,
                                              description="Start date for the report period (YYYY-MM-DD). If not provided with end_date, defaults to current month."),
        end_date: Optional[dt.date] = Query(None,
                                            description="End date for the report period (YYYY-MM-DD). If not provided with start_date, defaults to current month.")
):
    user_id = current_user.id
    today = dt.date.today()
    effective_start_date = start_date
    effective_end_date = end_date

    if start_date is None and end_date is None:
        effective_start_date = today.replace(day=1)
        effective_end_date = (today.replace(day=1) + relativedelta(months=1)) - relativedelta(days=1)
        log.info(
            f"User {user_id}: No date range for summary, defaulting to current month: {effective_start_date} to {effective_end_date}")
    elif start_date and not end_date:
        effective_end_date = (start_date.replace(day=1) + relativedelta(months=1)) - relativedelta(days=1)
    elif end_date and not start_date:
        effective_start_date = end_date.replace(day=1)

    if effective_start_date and effective_end_date and effective_start_date > effective_end_date:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Start date cannot be after end date.")

    log.info(
        f"User {user_id}: Request for full financial summary. Period: {effective_start_date} to {effective_end_date}")

    try:
        current_period_db_transactions = db_supabase.get_all_transactions(
            user_id=user_id, start_date=effective_start_date, end_date=effective_end_date, data_context='business'
        )
        current_period_insights_transactions: List[
            insights.Transaction] = current_period_db_transactions  # type: ignore

        previous_period_insights_transactions: Optional[List[insights.Transaction]] = None
        if effective_start_date and effective_end_date:
            num_days_in_current_period = (effective_end_date - effective_start_date).days + 1
            prev_period_end_date = effective_start_date - dt.timedelta(days=1)
            prev_period_start_date = prev_period_end_date - dt.timedelta(days=num_days_in_current_period - 1)

            previous_period_db_transactions = db_supabase.get_all_transactions(
                user_id=user_id, start_date=prev_period_start_date, end_date=prev_period_end_date,
                data_context='business'
            )
            previous_period_insights_transactions = previous_period_db_transactions  # type: ignore

        full_insights_data = insights.calculate_summary_insights(
            current_period_transactions=current_period_insights_transactions,
            previous_period_transactions=previous_period_insights_transactions
        )
        return FullInsightsReportPydantic(**full_insights_data)
    except Exception as e:
        log.error(f"User {user_id}: Error generating full financial summary: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to generate financial summary.")


@router.get("/insights/monthly-revenue-trend",
            response_model=MonthlyRevenueTrendResponsePydantic,
            summary="Get monthly revenue trend for the past N months and current month-to-date")
async def get_monthly_revenue_trend_api(
        current_user: UserPydantic = Depends(get_current_supabase_user),
        num_months: int = Query(6, ge=1, le=24,
                                description="Number of past full months to include in the trend (1-24)."),
        data_context: Optional[str] = Query("business", description="Data context (e.g., 'business', 'personal').")
):
    user_id = current_user.id
    log.info(f"User {user_id}: Request for monthly revenue trend for {num_months} past months. Context: {data_context}")
    try:
        trend_data_items = insights.calculate_monthly_revenue_trend(
            user_id=user_id, num_past_months=num_months, data_context=data_context
        )
        return MonthlyRevenueTrendResponsePydantic(trend_data=trend_data_items)  # type: ignore
    except Exception as e:
        log.error(f"User {user_id}: Error generating monthly revenue trend: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to generate monthly revenue trend.")


# --- NEW AI Query Endpoint ---
@router.post("/insights/ai-query",
             response_model=LLMQueryResponse,
             summary="Ask a financial question to the AI assistant")
async def ask_ai_financial_assistant(
        query_request: LLMQueryRequest,  # Request body with the user's question
        current_user: UserPydantic = Depends(get_current_supabase_user),
        # Optional date range for context, defaults to a wide range if not provided
        start_date: Optional[dt.date] = Query(None, description="Start date for AI context (YYYY-MM-DD)"),
        end_date: Optional[dt.date] = Query(None, description="End date for AI context (YYYY-MM-DD)")
):
    user_id = current_user.id
    log.info(f"User {user_id}: AI Query received: '{query_request.query}'. Date range: {start_date} to {end_date}")

    # Determine date range for fetching data
    # If no dates provided, use a default range (e.g., last N days from config)
    effective_start_date = start_date
    effective_end_date = end_date

    if not effective_start_date or not effective_end_date:
        today = dt.date.today()
        effective_end_date = today  # Default end date to today
        effective_start_date = today - dt.timedelta(days=settings.DEFAULT_LLM_CONTEXT_DAYS)  # Default start N days ago
        log.info(f"User {user_id}: AI Query using default date range: {effective_start_date} to {effective_end_date}")

    try:
        # 1. Fetch relevant transactions for the period
        # The llm_service expects parser.Transaction objects. db_supabase.Transaction should be compatible.
        db_transactions = db_supabase.get_all_transactions(
            user_id=user_id,
            start_date=effective_start_date,
            end_date=effective_end_date,
            data_context='business'  # Assuming business context for AI queries for now
        )
        # Ensure transactions are in the format expected by llm_service
        # This might involve converting db_supabase.Transaction to llm_service.Transaction if they differ significantly
        # For now, assuming they are compatible enough or llm_service.Transaction is a superset.
        llm_transactions: List[llm_service.Transaction] = []
        for db_tx in db_transactions:
            # Manual mapping if structures are different or to ensure all fields exist
            # This is crucial if llm_service.Transaction has fields not in db_supabase.Transaction
            # For simplicity, if db_supabase.Transaction has all fields that llm_service.Transaction might use,
            # direct conversion or careful attribute access in llm_service is needed.
            # Let's assume direct attribute access is safe for now, or llm_service handles missing ones.
            llm_transactions.append(
                llm_service.Transaction(  # Explicitly create llm_service.Transaction
                    id=db_tx.id,
                    date=db_tx.date,
                    description=db_tx.description,
                    amount=db_tx.amount,
                    category=db_tx.category,
                    transaction_type=db_tx.transaction_type,
                    source_account_type=db_tx.source_account_type,
                    source_filename=db_tx.source_filename,
                    raw_description=db_tx.raw_description
                    # Add other fields if llm_service.Transaction expects them
                )
            )
        log.debug(f"User {user_id}: Fetched {len(llm_transactions)} transactions for AI context.")

        # 2. Generate summary statistics for the period (optional, but good for context)
        # The llm_service.format_summary_for_qa expects a specific structure.
        # We'll use calculate_summary_insights and then adapt its output if needed,
        # or llm_service can adapt it. For now, let's pass the full summary.
        insights_transactions: List[insights.Transaction] = db_transactions  # type: ignore
        summary_for_llm_period = insights.calculate_summary_insights(current_period_transactions=insights_transactions)

        # Adapt summary_for_llm_period to the structure expected by llm_service.format_summary_for_qa
        # format_summary_for_qa expects: operational_income, operational_spending, net_operational_flow, net_spending_by_category, transaction_count
        adapted_summary_for_llm = {
            "operational_income": summary_for_llm_period.get("total_income"),  # Assuming total_income is operational
            "operational_spending": summary_for_llm_period.get("total_spending"),  # total_spending is negative
            "net_operational_flow": summary_for_llm_period.get("net_flow_operational"),
            "net_spending_by_category": {
                # Convert spending_by_category (negative values) to positive for "net spending"
                cat: str(abs(Decimal(val))) for cat, val in
                summary_for_llm_period.get("spending_by_category", {}).items() if Decimal(val) < 0
            },
            "transaction_count": summary_for_llm_period.get("total_transactions")
        }
        log.debug(f"User {user_id}: Generated summary for AI context: {adapted_summary_for_llm}")

        # 3. Call the LLM service
        # The llm_service.answer_financial_question returns a tuple (answer_text, status_str)
        answer_text, answer_status = llm_service.answer_financial_question(
            question=query_request.query,
            transactions=llm_transactions,  # Pass the list of llm_service.Transaction objects
            summary_data=adapted_summary_for_llm,  # Pass the adapted summary
            start_date_str=effective_start_date.isoformat() if effective_start_date else None,
            end_date_str=effective_end_date.isoformat() if effective_end_date else None
            # pre_calculated_result can be added if specific calculations are done here first
        )

        log.info(f"User {user_id}: AI Response status: {answer_status}, Answer: {answer_text[:100]}...")

        return LLMQueryResponse(question=query_request.query, answer=answer_text, status=answer_status)

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"User {user_id}: Error processing AI query '{query_request.query}': {e}", exc_info=True)
        # Log the failed query to the database for review
        db_supabase.log_llm_failed_query(
            user_id=user_id,
            query_text=query_request.query,
            llm_response=None,  # Or some error string if available before LLM call
            reason=f"Internal server error: {type(e).__name__}"
        )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to get response from AI assistant.")


# --- END NEW AI Query Endpoint ---


log.info("insights_router.py loaded. Router object should be defined.")

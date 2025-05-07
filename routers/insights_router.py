# routers/insights_router.py
import logging
import datetime as dt
from typing import Optional, List
from dateutil.relativedelta import relativedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status  # Added status

# Project specific imports
from models_pydantic import UserPydantic, FullInsightsReportPydantic
import database_supabase as db_supabase
import insights
from auth.dependencies import get_current_supabase_user

router = APIRouter(
    # prefix="/api/v1/insights", # REMOVED incorrect prefix
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
            summary="Get comprehensive financial insights for the current user")  # Added prefix here
async def get_full_financial_summary(
        current_user: UserPydantic = Depends(get_current_supabase_user),
        start_date: Optional[dt.date] = Query(None, description="Start date for the report period (YYYY-MM-DD)"),
        end_date: Optional[dt.date] = Query(None, description="End date for the report period (YYYY-MM-DD)")
):
    user_id = current_user.id
    log.info(f"User {user_id}: Request for full financial summary. Period: {start_date} to {end_date}")

    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Start date cannot be after end date.")  # Use status here

    try:
        current_period_db_transactions: List[db_supabase.Transaction] = db_supabase.get_all_transactions(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date
        )
        log.debug(f"User {user_id}: Fetched {len(current_period_db_transactions)} transactions for current period.")
        current_period_insights_transactions = current_period_db_transactions

        previous_period_insights_transactions: Optional[List[insights.Transaction]] = None

        if start_date and end_date:
            num_months = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
            if end_date.day < start_date.day and num_months > 0: num_months -= 1
            if num_months < 0: num_months = 0

            if num_months == 0:
                duration_current_period_days = (end_date - start_date).days + 1
                prev_period_end_date = start_date - dt.timedelta(days=1)
                prev_period_start_date = prev_period_end_date - dt.timedelta(days=duration_current_period_days - 1)
            else:
                prev_period_end_date = start_date - dt.timedelta(days=1)
                prev_period_start_date = prev_period_end_date - relativedelta(months=num_months,
                                                                              days=(end_date.day - start_date.day))
                if start_date.day == 1 and end_date == (
                        start_date + relativedelta(months=num_months + 1) - dt.timedelta(days=1)):
                    prev_period_start_date = prev_period_end_date.replace(day=1) - relativedelta(months=num_months)
                    prev_period_end_date = prev_period_start_date + relativedelta(months=num_months + 1) - dt.timedelta(
                        days=1)

            log.info(
                f"User {user_id}: Calculating previous period: {prev_period_start_date.isoformat()} to {prev_period_end_date.isoformat()}")
            previous_period_db_transactions = db_supabase.get_all_transactions(
                user_id=user_id,
                start_date=prev_period_start_date,
                end_date=prev_period_end_date
            )
            log.debug(
                f"User {user_id}: Fetched {len(previous_period_db_transactions or [])} transactions for previous period.")
            previous_period_insights_transactions = previous_period_db_transactions

        full_insights_data = insights.calculate_summary_insights(
            current_period_transactions=current_period_insights_transactions,
            previous_period_transactions=previous_period_insights_transactions
        )

        return FullInsightsReportPydantic(**full_insights_data)

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"User {user_id}: Error generating full financial summary: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to generate financial summary.")  # Use status here


# Add other insight endpoints here later if needed, ensuring the path starts with /insights/
# e.g. @router.get("/insights/trends/monthly", ...)

print("insights_router.py loaded. Router object should be defined.")
if 'router' in globals() and router is not None:
    print("insights_router.router IS defined.")
else:
    print("insights_router.router IS NOT defined (APIRouter instantiation likely failed or name mismatch).")


# models_pydantic.py
from pydantic import BaseModel, EmailStr, Field, RootModel
from typing import Optional, List, Dict, Any
import datetime as dt
from decimal import Decimal

# --- User and Auth Models ---
class UserBasePydantic(BaseModel):
    email: EmailStr

class UserCreatePydantic(UserBasePydantic):
    password: str = Field(..., min_length=8, description="User password, minimum 8 characters.")

class UserPydantic(UserBasePydantic):
    id: str
    username: Optional[str] = None
    class Config:
        from_attributes = True

class TokenPydantic(BaseModel):
    access_token: str
    token_type: str
    refresh_token: Optional[str] = None
    user: Optional[UserPydantic] = None

# --- Transaction Models ---
class TransactionPydantic(BaseModel):
    id: Optional[int] = None
    user_id: str
    date: dt.date
    description: str
    amount: str
    category: Optional[str] = None
    transaction_type: Optional[str] = None
    raw_description: Optional[str] = None
    client_name: Optional[str] = None
    invoice_id: Optional[str] = None
    project_id: Optional[str] = None
    payout_source: Optional[str] = None
    transaction_origin: Optional[str] = None
    data_context: Optional[str] = None
    rate: Optional[str] = None
    quantity: Optional[str] = None
    invoice_status: Optional[str] = None
    date_paid: Optional[dt.date] = None
    created_at: Optional[dt.datetime] = None
    updated_at: Optional[dt.datetime] = None
    class Config:
        from_attributes = True

class CategoryUpdatePydantic(BaseModel):
    new_category: str = Field(..., min_length=1, description="The new category name for the transaction.")


# --- Insights Report Models ---
class ExecutiveSummaryPydantic(BaseModel):
    total_income: str
    total_expenses: str
    total_outstanding_invoices: Optional[str] = None
    total_overdue_invoices: Optional[str] = None
    top_client_by_revenue: Optional[Dict[str, str]] = None
    top_service_by_revenue: Optional[Dict[str, str]] = None
    top_project_by_revenue: Optional[Dict[str, str]] = None
    best_rate_client: Optional[Dict[str, str]] = None
    top_expense_category: Optional[Dict[str, str]] = None

class ClientRateDetailPydantic(BaseModel):
    average_rate: str
    max_rate: str
    min_rate: str
    num_transactions_with_rate: str

class ClientRateAnalysisPydantic(BaseModel):
    rates_by_client: Dict[str, ClientRateDetailPydantic]
    best_average_rate_client: Optional[Dict[str, str]] = None

class PaymentStatusBreakdownPydantic(BaseModel):
    by_status: Dict[str, str]
    total_outstanding: str
    total_overdue: str

class PreviousPeriodChangeDetailPydantic(BaseModel):
    current: str
    previous: str
    change_amount: str
    percent_change: Optional[float] = None

class PreviousPeriodComparisonPydantic(BaseModel):
    previous_total_income: str
    previous_total_spending: str
    previous_net_flow_operational: str
    changes: Dict[str, PreviousPeriodChangeDetailPydantic]

class FullInsightsReportPydantic(BaseModel):
    total_transactions: int
    period_start_date: Optional[str] = None
    period_end_date: Optional[str] = None
    total_income: str
    total_spending: str
    net_flow_operational: str
    net_change_total: Optional[str] = None
    spending_by_category: Dict[str, str]
    income_by_category: Dict[str, str]
    revenue_by_client: Dict[str, str]
    revenue_by_service: Dict[str, str]
    revenue_by_project: Dict[str, str]
    client_rate_analysis: ClientRateAnalysisPydantic
    payment_status_summary: PaymentStatusBreakdownPydantic
    average_transaction_amount: Optional[str] = None
    median_transaction_amount: Optional[str] = None
    executive_summary: ExecutiveSummaryPydantic
    previous_period_comparison: Optional[PreviousPeriodComparisonPydantic] = None

# --- Monthly Revenue Trend Models ---
class MonthlyRevenueDataItemPydantic(BaseModel):
    month: str
    revenue: float
    isCurrent: Optional[bool] = None
    class Config:
        from_attributes = True

class MonthlyRevenueTrendResponsePydantic(BaseModel):
    trend_data: List[MonthlyRevenueDataItemPydantic]

# --- LLM and Feedback Models ---
class LLMQueryRequest(BaseModel):
    """Request model for querying the LLM financial assistant."""
    query: str = Field(..., min_length=3, description="User's question for the financial assistant.")

class LLMQueryResponse(BaseModel):
    """Response model from the LLM financial assistant."""
    question: str
    answer: str
    status: Optional[str] = "success" # e.g., success, error, cannot_answer, blocked

class FeedbackReportPydantic(BaseModel):
    query: str
    incorrect_response: str
    user_comment: Optional[str] = None

class FeedbackGeneralPydantic(BaseModel):
    feedback_type: Optional[str] = None
    comment: str = Field(..., min_length=10, description="Detailed feedback comment.")
    contact_email: Optional[EmailStr] = None

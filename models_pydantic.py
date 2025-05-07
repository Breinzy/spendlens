# models_pydantic.py
from pydantic import BaseModel, EmailStr, Field, RootModel
from typing import Optional, List, Dict, Any
import datetime as dt
from decimal import Decimal

# --- User and Auth Models ---
class UserBasePydantic(BaseModel):
    email: EmailStr

class UserCreatePydantic(UserBasePydantic):
    password: str = Field(..., min_length=8)

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
    rate: Optional[str] = None
    quantity: Optional[str] = None
    invoice_status: Optional[str] = None
    date_paid: Optional[dt.date] = None
    created_at: Optional[dt.datetime] = None
    updated_at: Optional[dt.datetime] = None
    class Config:
        from_attributes = True

class CategoryUpdatePydantic(BaseModel): # New model for updating category
    new_category: str = Field(..., min_length=1)


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

# Other existing models (SummaryPydantic, MonthlyTrendsPydantic etc. can remain or be deprecated)
# ... (omitted for brevity, assume they are the same as models_pydantic_v2)
class SpendingByCategoryPydantic(RootModel[Dict[str, str]]): pass
class SummaryPydantic(BaseModel):
    total_transactions: int; period_start_date: Optional[dt.date] = None; period_end_date: Optional[dt.date] = None
    total_income: str; total_spending: str; total_payments_transfers: Optional[str] = None
    net_flow_operational: str; net_change_total: Optional[str] = None
    spending_by_category: SpendingByCategoryPydantic; income_by_category: SpendingByCategoryPydantic
    average_transaction_amount: Optional[str] = None; median_transaction_amount: Optional[str] = None
class MonthlyTrendDetailPydantic(BaseModel):
    current_amount: str; previous_amount: str; change: str; percent_change: Optional[float] = None
class MonthlyTrendComparisonPydantic(BaseModel):
    current_month_str: str; previous_month_str: str; total_current_spending: str; total_previous_spending: str
    total_change: str; total_percent_change: Optional[float] = None; comparison: Dict[str, MonthlyTrendDetailPydantic]
class MonthlySpendingDataPydantic(RootModel[Dict[str, Dict[str, str]]]): pass
class MonthlyTrendsPydantic(BaseModel):
    start_date: Optional[dt.date] = None; end_date: Optional[dt.date] = None
    monthly_spending: MonthlySpendingDataPydantic; trend_comparison: Optional[MonthlyTrendComparisonPydantic] = None
class RecurringTransactionGroupPydantic(BaseModel):
    description: str; category: Optional[str] = None; average_amount: str
    count: int; interval_days: Optional[int] = None; transactions: List[TransactionPydantic]
class RecurringTransactionsPydantic(BaseModel): recurring_groups: List[RecurringTransactionGroupPydantic]
class ClientSummaryDetailPydantic(BaseModel):
    total_revenue: str; total_direct_cost: str; net_from_client: str
class ClientBreakdownResponsePydantic(RootModel[Dict[str, ClientSummaryDetailPydantic]]): pass
class UniqueClientResponsePydantic(BaseModel): clients: List[str]
class LLMQueryRequest(BaseModel): query: str = Field(..., min_length=3)
class LLMQueryResponse(BaseModel): question: str; answer: str; status: Optional[str] = "success"
class FeedbackReportPydantic(BaseModel): query: str; incorrect_response: str; user_comment: Optional[str] = None
class FeedbackGeneralPydantic(BaseModel):
    feedback_type: Optional[str] = None; comment: str = Field(..., min_length=10); contact_email: Optional[EmailStr] = None


# models_pydantic.py
from pydantic import BaseModel, EmailStr, Field, RootModel
from typing import Optional, List, Dict, Any
from uuid import UUID
import datetime as dt
from decimal import Decimal

class UserBasePydantic(BaseModel):
    email: EmailStr

class UserCreatePydantic(UserBasePydantic):
    password: str = Field(..., min_length=8)

class UserPydantic(UserBasePydantic):
    id: str
    username: Optional[str] = None
    class Config: from_attributes = True

class TokenPydantic(BaseModel):
    access_token: str
    token_type: str
    refresh_token: Optional[str] = None
    user: Optional[UserPydantic] = None

class TransactionPydantic(BaseModel): # Simplified for this example, ensure all fields from db.Transaction are here
    id: int
    user_id: str
    date: dt.date
    description: str
    amount: str # String representation of Decimal
    category: str
    transaction_type: Optional[str] = None
    raw_description: Optional[str] = None
    client_name: Optional[str] = None
    invoice_id: Optional[str] = None
    project_id: Optional[str] = None
    payout_source: Optional[str] = None
    transaction_origin: Optional[str] = None
    created_at: Optional[dt.datetime] = None
    updated_at: Optional[dt.datetime] = None
    class Config: from_attributes = True

# --- Insights Models (as before) ---
class SpendingByCategoryPydantic(RootModel[Dict[str, str]]): pass

class SummaryPydantic(BaseModel):
    total_transactions: int
    period_start_date: Optional[dt.date] = None
    period_end_date: Optional[dt.date] = None
    total_income: str
    total_spending: str
    total_payments_transfers: Optional[str] = None
    net_flow_operational: str
    net_change_total: Optional[str] = None
    spending_by_category: SpendingByCategoryPydantic
    income_by_category: SpendingByCategoryPydantic
    average_transaction_amount: Optional[str] = None
    median_transaction_amount: Optional[str] = None

class MonthlyTrendDetailPydantic(BaseModel):
    current_amount: str; previous_amount: str; change: str
    percent_change: Optional[float] = None

class MonthlyTrendComparisonPydantic(BaseModel):
    current_month_str: str; previous_month_str: str
    total_current_spending: str; total_previous_spending: str
    total_change: str; total_percent_change: Optional[float] = None
    comparison: Dict[str, MonthlyTrendDetailPydantic]

class MonthlySpendingDataPydantic(RootModel[Dict[str, Dict[str, str]]]): pass

class MonthlyTrendsPydantic(BaseModel):
    start_date: Optional[dt.date] = None; end_date: Optional[dt.date] = None
    monthly_spending: MonthlySpendingDataPydantic
    trend_comparison: Optional[MonthlyTrendComparisonPydantic] = None

class RecurringTransactionGroupPydantic(BaseModel):
    description: str; category: Optional[str] = None; average_amount: str
    count: int; interval_days: Optional[int] = None
    transactions: List[TransactionPydantic] # Changed to use TransactionPydantic

class RecurringTransactionsPydantic(BaseModel):
    recurring_groups: List[RecurringTransactionGroupPydantic]

# --- New Client Breakdown Models ---
class ClientSummaryDetailPydantic(BaseModel):
    total_revenue: str # String representation of Decimal
    total_direct_cost: str # String representation of Decimal (will be negative or zero)
    net_from_client: str # String representation of Decimal

class ClientBreakdownResponsePydantic(RootModel[Dict[str, ClientSummaryDetailPydantic]]):
    # Root model where keys are client names, values are their summary details
    pass

class UniqueClientResponsePydantic(BaseModel):
    clients: List[str]

# --- LLM & Feedback Models (as before) ---
class LLMQueryRequest(BaseModel):
    query: str = Field(..., min_length=3)

class LLMQueryResponse(BaseModel):
    question: str; answer: str; status: str

class FeedbackReportPydantic(BaseModel):
    query: str; incorrect_response: str; user_comment: Optional[str] = None

class FeedbackGeneralPydantic(BaseModel):
    feedback_type: Optional[str] = None; comment: str = Field(..., min_length=10)
    contact_email: Optional[EmailStr] = None

# models_pydantic.py
from pydantic import BaseModel, EmailStr, Field, RootModel # RootModel for dict-based models
from typing import Optional, List, Dict, Any
import datetime as dt
from decimal import Decimal # Ensure Decimal is imported

# --- User and Auth Models ---
class UserBasePydantic(BaseModel):
    """Base model for user data, primarily for email validation."""
    email: EmailStr

class UserCreatePydantic(UserBasePydantic):
    """Model for creating a new user, includes password."""
    password: str = Field(..., min_length=8, description="User password, minimum 8 characters.")

class UserPydantic(UserBasePydantic):
    """Model representing a user, including their ID and username."""
    id: str
    username: Optional[str] = None

    class Config:
        from_attributes = True # Enables ORM mode (Pydantic V2)

class TokenPydantic(BaseModel):
    """Model for authentication tokens."""
    access_token: str
    token_type: str
    refresh_token: Optional[str] = None
    user: Optional[UserPydantic] = None # Optionally include user details with the token

# --- Transaction Models ---
class TransactionPydantic(BaseModel):
    """Model representing a financial transaction for API responses and requests."""
    id: Optional[int] = None # Transaction ID, optional for creation
    user_id: str # Associated user ID
    date: dt.date # Transaction date
    description: str # Transaction description
    amount: str # Transaction amount, stored as string for precision, converted to Decimal in backend
    category: Optional[str] = None # Transaction category
    transaction_type: Optional[str] = None # e.g., DEBIT, CREDIT
    raw_description: Optional[str] = None # Original description before any processing
    client_name: Optional[str] = None # Client associated with the transaction
    invoice_id: Optional[str] = None # Invoice ID, if applicable
    project_id: Optional[str] = None # Project ID, if applicable
    payout_source: Optional[str] = None # Source of payout, e.g., Stripe, PayPal
    transaction_origin: Optional[str] = None # Origin of the transaction data, e.g., 'chase_checking', 'freshbooks_invoice'
    data_context: Optional[str] = None # NEW FIELD: e.g., 'business', 'personal'
    rate: Optional[str] = None # Rate for services, if applicable (as string)
    quantity: Optional[str] = None # Quantity for services/items (as string)
    invoice_status: Optional[str] = None # Status of an invoice, e.g., 'paid', 'sent', 'overdue'
    date_paid: Optional[dt.date] = None # Date an invoice was paid
    created_at: Optional[dt.datetime] = None # Timestamp of creation
    updated_at: Optional[dt.datetime] = None # Timestamp of last update

    class Config:
        from_attributes = True # Enables ORM mode

class CategoryUpdatePydantic(BaseModel):
    """Model for updating a transaction's category."""
    new_category: str = Field(..., min_length=1, description="The new category name for the transaction.")


# --- Insights Report Models (Comprehensive V2 Structure) ---
class ExecutiveSummaryPydantic(BaseModel):
    """Key highlights for an executive summary view."""
    total_income: str
    total_expenses: str # Should be positive representation of spending
    total_outstanding_invoices: Optional[str] = None
    total_overdue_invoices: Optional[str] = None
    top_client_by_revenue: Optional[Dict[str, str]] = None # {"name": "Client X", "amount": "1200.00"}
    top_service_by_revenue: Optional[Dict[str, str]] = None # {"name": "Web Dev", "amount": "800.00"}
    top_project_by_revenue: Optional[Dict[str, str]] = None # {"name": "Project Alpha", "amount": "1500.00"}
    best_rate_client: Optional[Dict[str, str]] = None # {"name": "Client Y", "average_rate": "150.00"}
    top_expense_category: Optional[Dict[str, str]] = None # {"name": "Software", "amount": "300.00"}

class ClientRateDetailPydantic(BaseModel):
    """Detailed rate information for a specific client."""
    average_rate: str
    max_rate: str
    min_rate: str
    num_transactions_with_rate: str

class ClientRateAnalysisPydantic(BaseModel):
    """Analysis of rates across different clients."""
    rates_by_client: Dict[str, ClientRateDetailPydantic] # Key is client name
    best_average_rate_client: Optional[Dict[str, str]] = None # {"name": "Client Y", "average_rate": "150.00"}

class PaymentStatusBreakdownPydantic(BaseModel):
    """Breakdown of invoice payment statuses."""
    by_status: Dict[str, str] # e.g., {"paid": "5000.00", "sent": "1200.00"}
    total_outstanding: str
    total_overdue: str

class PreviousPeriodChangeDetailPydantic(BaseModel):
    """Details of change for a metric compared to a previous period."""
    current: str
    previous: str
    change_amount: str
    percent_change: Optional[float] = None # e.g., 10.5 for 10.5% increase, -5.2 for 5.2% decrease

class PreviousPeriodComparisonPydantic(BaseModel):
    """Comparison of key metrics with a previous period."""
    previous_total_income: str
    previous_total_spending: str # Positive representation
    previous_net_flow_operational: str
    changes: Dict[str, PreviousPeriodChangeDetailPydantic] # Keys: "total_income", "total_spending", "net_flow_operational"

class FullInsightsReportPydantic(BaseModel):
    """Comprehensive financial insights report model for V2."""
    total_transactions: int
    period_start_date: Optional[str] = None # ISO format string
    period_end_date: Optional[str] = None # ISO format string
    total_income: str
    total_spending: str # Positive representation of spending
    net_flow_operational: str # Income - Operational Spending
    net_change_total: Optional[str] = None # Overall change including all transaction types
    spending_by_category: Dict[str, str] # Category name to positive spending amount string
    income_by_category: Dict[str, str] # Category name to income amount string
    revenue_by_client: Dict[str, str] # Client name to revenue amount string
    revenue_by_service: Dict[str, str] # Service/item description to revenue amount string
    revenue_by_project: Dict[str, str] # Project ID/name to revenue amount string
    client_rate_analysis: ClientRateAnalysisPydantic
    payment_status_summary: PaymentStatusBreakdownPydantic
    average_transaction_amount: Optional[str] = None
    median_transaction_amount: Optional[str] = None
    executive_summary: ExecutiveSummaryPydantic
    previous_period_comparison: Optional[PreviousPeriodComparisonPydantic] = None

# --- Simplified/Older Insight Models (can be deprecated or kept for specific use cases) ---
# Using RootModel for direct dictionary to model conversion where the structure is simple.
class SpendingByCategoryPydantic(RootModel[Dict[str, str]]):
    """Represents spending amounts keyed by category name."""
    pass

class SummaryPydantic(BaseModel): # Potentially an older or more focused summary
    """Basic summary of financial data."""
    total_transactions: int
    period_start_date: Optional[dt.date] = None
    period_end_date: Optional[dt.date] = None
    total_income: str
    total_spending: str # Positive representation
    total_payments_transfers: Optional[str] = None # Positive representation
    net_flow_operational: str
    net_change_total: Optional[str] = None
    spending_by_category: SpendingByCategoryPydantic
    income_by_category: SpendingByCategoryPydantic # Using the RootModel for income as well
    average_transaction_amount: Optional[str] = None
    median_transaction_amount: Optional[str] = None

class MonthlyTrendDetailPydantic(BaseModel):
    """Details for a category in monthly trend comparison."""
    current_amount: str # Positive representation
    previous_amount: str # Positive representation
    change: str # Difference, can be negative
    percent_change: Optional[float] = None

class MonthlyTrendComparisonPydantic(BaseModel):
    """Comparison of spending trends between two months."""
    current_month_str: str # e.g., "2023-04"
    previous_month_str: str # e.g., "2023-03"
    total_current_spending: str # Positive representation
    total_previous_spending: str # Positive representation
    total_change: str # Difference, can be negative
    total_percent_change: Optional[float] = None
    comparison: Dict[str, MonthlyTrendDetailPydantic] # Category name to trend details

class MonthlySpendingDataPydantic(RootModel[Dict[str, Dict[str, str]]]):
    """Monthly spending data, keyed by month string (YYYY-MM), then category."""
    pass

class MonthlyTrendsPydantic(BaseModel):
    """Overall monthly spending trends."""
    start_date: Optional[dt.date] = None
    end_date: Optional[dt.date] = None
    monthly_spending: MonthlySpendingDataPydantic
    trend_comparison: Optional[MonthlyTrendComparisonPydantic] = None

class RecurringTransactionGroupPydantic(BaseModel):
    """Details of an identified group of recurring transactions."""
    description: str
    category: Optional[str] = None
    average_amount: str
    count: int
    interval_days: Optional[int] = None
    transactions: List[TransactionPydantic] # List of actual transactions in the group

class RecurringTransactionsPydantic(BaseModel):
    """Container for all identified recurring transaction groups."""
    recurring_groups: List[RecurringTransactionGroupPydantic]

class ClientSummaryDetailPydantic(BaseModel):
    """Summary of revenue and costs for a specific client."""
    total_revenue: str
    total_direct_cost: str # Should be positive representation of costs
    net_from_client: str

class ClientBreakdownResponsePydantic(RootModel[Dict[str, ClientSummaryDetailPydantic]]):
    """Response model for client breakdown, client name to summary details."""
    pass

class UniqueClientResponsePydantic(BaseModel):
    """Response model for a list of unique client names."""
    clients: List[str]

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
    """Model for reporting an error in an LLM response."""
    query: str
    incorrect_response: str
    user_comment: Optional[str] = None

class FeedbackGeneralPydantic(BaseModel):
    """Model for submitting general feedback about the application."""
    feedback_type: Optional[str] = None # e.g., "bug", "feature_request", "general"
    comment: str = Field(..., min_length=10, description="Detailed feedback comment.")
    contact_email: Optional[EmailStr] = None # Optional email for follow-up

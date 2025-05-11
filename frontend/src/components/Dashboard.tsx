// src/components/Dashboard.tsx
import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';

// Import UI components using relative paths
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "../components/ui/alert";

// Import charting library
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Legend, CartesianGrid, PieChart, Pie, Cell, LineChart, Line } from 'recharts'; // Added LineChart, Line

// Import icons
import {
  DollarSign, TrendingUp, TrendingDown, RefreshCw, AlertCircle, Upload,
  Users, ShoppingCart, Briefcase, Lightbulb, BarChart2, ListChecks, Percent, CalendarDays
} from 'lucide-react'; // Added CalendarDays

// --- Constants ---
const API_BASE_URL = '/api/v1';

// --- Interfaces/Types ---
interface ChangeDetail {
    current: string;
    previous: string;
    change_amount: string;
    percent_change: number | null;
}

interface PreviousPeriodComparison {
    previous_total_income: string;
    previous_total_spending: string;
    previous_net_flow_operational: string;
    changes: {
        total_income?: ChangeDetail;
        total_spending?: ChangeDetail;
        net_flow_operational?: ChangeDetail;
    };
}

interface MonthlyRevenueData {
    month: string; // e.g., "2025-01", "Current"
    revenue: number;
    isCurrent?: boolean; // Flag for current month-to-date
}

interface FinancialSummary {
  // These will now represent the "current month"
  total_transactions: number;
  period_start_date?: string | null; // Will be start of current month
  period_end_date?: string | null;   // Will be end of current month
  total_income: string;
  total_spending: string;
  net_flow_operational: string;
  spending_by_category: Record<string, string>;
  income_by_category: Record<string, string>;
  revenue_by_client: Record<string, string>;
  revenue_by_project: Record<string, string>;
  executive_summary?: {
    top_expense_category?: { name: string; amount: string };
    top_client_by_revenue?: { name: string; amount: string };
  };
  previous_period_comparison?: PreviousPeriodComparison | null; // This will be "current month vs. last month"
}

// --- Helper Functions ---
const formatCurrency = (value: number | string | undefined | null, showSign = true): string => {
  const numberValue = typeof value === 'string' ? parseFloat(value) : value;
  if (numberValue === null || numberValue === undefined || isNaN(numberValue)) {
    return showSign ? '$0.00' : '0.00';
  }
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(numberValue);
};

const getTopItem = (data: Record<string, string> | undefined, takeAbsoluteValue = false): { name: string; amount: number } | null => {
  if (!data || Object.keys(data).length === 0) return null;
  let topItem: { name: string; amount: number } | null = null;
  for (const [key, valueStr] of Object.entries(data)) {
    try {
      let amount = parseFloat(valueStr);
      if (takeAbsoluteValue) amount = Math.abs(amount);
      if (!topItem || amount > topItem.amount) topItem = { name: key, amount: amount };
    } catch (e) { console.warn(`Could not parse amount for ${key}: ${valueStr}`); }
  }
  return topItem;
};

const PercentageChange = ({ change, invertColorLogic = false }: { change: ChangeDetail | undefined, invertColorLogic?: boolean }) => {
    if (!change || change.percent_change === null || change.percent_change === undefined) {
        return <span className="text-xs text-slate-500 dark:text-slate-400">vs last month N/A</span>;
    }
    let isPositiveEffect = change.percent_change >= 0;
    if (invertColorLogic) isPositiveEffect = change.percent_change <= 0; // For expenses, decrease is good

    const colorClass = isPositiveEffect ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400";

    return (
        <span className={`text-xs font-medium ${colorClass}`}>
            {change.percent_change >= 0 ? '+' : ''}{change.percent_change.toFixed(1)}% vs last month
        </span>
    );
};

interface DashboardProps {
    navigateToUpload: () => void;
}

export default function DashboardComponent({ navigateToUpload }: DashboardProps) {
    const { user, token, logout } = useAuth();
    const [currentMonthSummary, setCurrentMonthSummary] = useState<FinancialSummary | null>(null);
    const [monthlyRevenueTrend, setMonthlyRevenueTrend] = useState<MonthlyRevenueData[]>([]);
    const [loadingSummary, setLoadingSummary] = useState<boolean>(true);
    const [loadingTrend, setLoadingTrend] = useState<boolean>(true); // Separate loading for trend
    const [error, setError] = useState<string | null>(null);

    const [currentDisplayMonth, setCurrentDisplayMonth] = useState(new Date());

    const fetchCurrentMonthSummary = useCallback(async (dateForMonth: Date) => {
        if (!token) {
            setError("Authentication token not available.");
            setLoadingSummary(false);
            return;
        }
        setLoadingSummary(true);
        setError(null);

        const year = dateForMonth.getFullYear();
        const month = dateForMonth.getMonth() + 1; // JS months are 0-indexed
        const startDate = `${year}-${String(month).padStart(2, '0')}-01`;
        const endDate = new Date(year, month, 0); // Last day of current month
        const endDateStr = `${year}-${String(month).padStart(2, '0')}-${String(endDate.getDate()).padStart(2, '0')}`;

        console.log(`Fetching summary for: ${startDate} to ${endDateStr}`);

        try {
            const response = await fetch(`${API_BASE_URL}/insights/summary?start_date=${startDate}&end_date=${endDateStr}`, {
                method: 'GET',
                headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
            });
            // ... (rest of fetchSummary logic from previous version, adapted for setCurrentMonthSummary) ...
            if (!response.ok) {
                const errorBody = await response.text();
                 if (response.status === 404 || (response.status === 500 && errorBody.toLowerCase().includes("no transaction"))) {
                    setCurrentMonthSummary(null);
                 } else {
                    throw new Error(`Failed to fetch summary: ${response.status} ${response.statusText}. ${errorBody}`);
                 }
            } else {
                 const data: FinancialSummary = await response.json();
                 if (data && typeof data.total_transactions === 'number') {
                    setCurrentMonthSummary(data);
                 } else {
                    console.warn("Received summary data but it seems incomplete or invalid.");
                    setCurrentMonthSummary(null);
                 }
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : "An unknown error occurred while fetching summary.");
            setCurrentMonthSummary(null);
        } finally {
            setLoadingSummary(false);
        }
    }, [token]);

    // --- MOCK FUNCTION FOR MONTHLY REVENUE TREND ---
    const fetchMonthlyRevenueTrend = useCallback(async () => {
        if (!token) return;
        setLoadingTrend(true);
        console.log("Fetching monthly revenue trend (currently mocked)...");
        // TODO: Replace with actual API call
        // Example: const response = await fetch(`${API_BASE_URL}/insights/monthly-revenue?months=6`, { headers: { 'Authorization': `Bearer ${token}` } });
        // const data = await response.json();
        // setMonthlyRevenueTrend(data);

        // Mock data for 6 previous months + current month-to-date
        await new Promise(resolve => setTimeout(resolve, 500)); // Simulate API delay
        const today = new Date();
        const mockData: MonthlyRevenueData[] = [];
        for (let i = 6; i > 0; i--) {
            const d = new Date(today.getFullYear(), today.getMonth() - i, 1);
            mockData.push({
                month: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`,
                revenue: Math.floor(Math.random() * (7000 - 2000 + 1)) + 2000,
            });
        }
        // Add current month's actual income (if available) or a smaller random value
        const currentMonthRevenue = currentMonthSummary ? parseFloat(currentMonthSummary.total_income) : Math.floor(Math.random() * 3000);
        mockData.push({
            month: 'Current',
            revenue: currentMonthRevenue || 0,
            isCurrent: true,
        });
        setMonthlyRevenueTrend(mockData);
        setLoadingTrend(false);
    }, [token, currentMonthSummary]);
    // --- END MOCK FUNCTION ---

    useEffect(() => {
        fetchCurrentMonthSummary(currentDisplayMonth);
    }, [fetchCurrentMonthSummary, currentDisplayMonth]);

    useEffect(() => {
        if (token) { // Only fetch trend if logged in
            fetchMonthlyRevenueTrend();
        }
    }, [fetchMonthlyRevenueTrend, token]); // Re-fetch if currentMonthSummary changes (to update "Current" bar)

    const isLoading = loadingSummary || loadingTrend;

    // Chart data for main cards (Income vs Expenses for the current month)
    const incomeExpenseChartData = currentMonthSummary ? [
        { name: 'Income', value: parseFloat(currentMonthSummary.total_income) || 0, fill: 'hsl(var(--chart-1))' },
        { name: 'Expenses', value: Math.abs(parseFloat(currentMonthSummary.total_spending)) || 0, fill: 'hsl(var(--chart-2))' },
    ] : [];

    const topSpendingCategory = getTopItem(currentMonthSummary?.spending_by_category, true);
    const topClientByRevenue = getTopItem(currentMonthSummary?.revenue_by_client);

    const spendingCategoriesChartData = currentMonthSummary?.spending_by_category
    ? Object.entries(currentMonthSummary.spending_by_category)
        .map(([name, valueStr]) => ({ name, value: Math.abs(parseFloat(valueStr)) || 0 }))
        .filter(item => item.value > 0)
        .sort((a, b) => b.value - a.value)
        .slice(0, 5)
    : [];
    const PIE_CHART_COLORS = ['hsl(var(--chart-1))', 'hsl(var(--chart-2))', 'hsl(var(--chart-3))', 'hsl(var(--chart-4))', 'hsl(var(--chart-5))'];

    const profitMargin = currentMonthSummary && parseFloat(currentMonthSummary.total_income) !== 0
        ? ((parseFloat(currentMonthSummary.net_flow_operational) / parseFloat(currentMonthSummary.total_income)) * 100)
        : null;

    const currentMonthName = currentDisplayMonth.toLocaleString('default', { month: 'long', year: 'numeric' });

    return (
        <div className="container mx-auto p-4 md:p-6 lg:p-8 min-h-screen bg-slate-100 dark:bg-slate-900 text-slate-900 dark:text-slate-50">
            <header className="flex flex-col sm:flex-row justify-between items-center mb-8 pb-4 border-b border-slate-200 dark:border-slate-700">
                <div className="mb-4 sm:mb-0">
                    <h1 className="text-3xl md:text-4xl font-bold text-slate-800 dark:text-slate-100">
                        Welcome, {user?.username || user?.email}!
                    </h1>
                    <p className="text-md text-slate-600 dark:text-slate-400">Your SpendLens Business Dashboard</p>
                </div>
                <div className="flex items-center space-x-3">
                    <Button onClick={navigateToUpload} variant="outline" size="sm" className="bg-white dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 border-slate-300 dark:border-slate-600">
                         <Upload className="mr-2 h-4 w-4" />
                         Upload Files
                    </Button>
                    <Button onClick={() => { fetchCurrentMonthSummary(currentDisplayMonth); fetchMonthlyRevenueTrend(); }} variant="outline" size="sm" disabled={isLoading} className="bg-white dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 border-slate-300 dark:border-slate-600">
                        <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
                        <span className="ml-2 hidden sm:inline">Refresh</span>
                    </Button>
                    <Button onClick={logout} variant="destructive" size="sm">
                        Log Out
                    </Button>
                </div>
            </header>

            <main className="space-y-10">
                {isLoading && (
                    <div className="flex justify-center items-center py-20">
                        <RefreshCw className="h-10 w-10 animate-spin text-blue-600 dark:text-blue-400" />
                        <p className="ml-4 text-xl text-slate-600 dark:text-slate-400">Loading financial data...</p>
                    </div>
                )}
                {error && !isLoading && (
                     <Alert variant="destructive" className="my-6 p-5">
                        <AlertCircle className="h-6 w-6" />
                        <AlertTitle className="text-lg font-semibold">Error Loading Dashboard</AlertTitle>
                        <AlertDescription className="mt-1">{error}</AlertDescription>
                     </Alert>
                )}

                {!isLoading && (currentMonthSummary || monthlyRevenueTrend.length > 0) && ( // Show sections if any data is available
                    <>
                        {/* Monthly Revenue Trend Chart Section */}
                        <section>
                            <h2 className="text-2xl font-semibold text-slate-700 dark:text-slate-200 mb-4">Monthly Revenue Trend</h2>
                            <Card className="shadow-lg dark:bg-slate-800">
                                <CardContent className="pt-6">
                                    {monthlyRevenueTrend.length > 0 ? (
                                        <ResponsiveContainer width="100%" height={300}>
                                            <BarChart data={monthlyRevenueTrend} margin={{ top: 5, right: 20, left: -10, bottom: 20 }}>
                                                <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200 dark:stroke-slate-700" vertical={false}/>
                                                <XAxis dataKey="month" angle={-30} textAnchor="end" height={50} tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 12 }}/>
                                                <YAxis tickFormatter={(value) => formatCurrency(value, false)} tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 12 }}/>
                                                <Tooltip
                                                    formatter={(value: number, name, props) => [formatCurrency(value), props.payload.isCurrent ? "Current MTD" : "Revenue"]}
                                                    contentStyle={{ backgroundColor: 'hsl(var(--popover))', border: '1px solid hsl(var(--border))', borderRadius: '0.5rem' }}
                                                    labelStyle={{ color: 'hsl(var(--popover-foreground))', fontWeight: 'bold' }}
                                                />
                                                <Bar dataKey="revenue" name="Revenue" radius={[4, 4, 0, 0]} maxBarSize={50}>
                                                    {monthlyRevenueTrend.map((entry, index) => (
                                                        <Cell key={`cell-${index}`} fill={entry.isCurrent ? 'hsl(var(--primary))' : 'hsl(var(--chart-3))'} />
                                                    ))}
                                                </Bar>
                                            </BarChart>
                                        </ResponsiveContainer>
                                    ) : (
                                        <p className="text-center text-slate-500 dark:text-slate-400 py-10">Revenue trend data is not available.</p>
                                    )}
                                </CardContent>
                            </Card>
                        </section>

                        {currentMonthSummary && (
                            <section>
                                <h2 className="text-2xl font-semibold text-slate-700 dark:text-slate-200 mb-6">
                                    Current Month Overview: <span className="text-blue-600 dark:text-blue-400">{currentMonthName}</span>
                                </h2>
                                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-6">
                                    <Card className="shadow-lg hover:shadow-xl transition-shadow duration-300 dark:bg-slate-800">
                                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                            <CardTitle className="text-sm font-medium text-slate-500 dark:text-slate-400">Income (This Month)</CardTitle>
                                            <TrendingUp className="h-5 w-5 text-green-500" />
                                        </CardHeader>
                                        <CardContent>
                                            <div className="text-3xl font-bold text-green-600 dark:text-green-400">
                                                {formatCurrency(currentMonthSummary.total_income)}
                                            </div>
                                            <PercentageChange change={currentMonthSummary.previous_period_comparison?.changes?.total_income} />
                                        </CardContent>
                                    </Card>
                                    <Card className="shadow-lg hover:shadow-xl transition-shadow duration-300 dark:bg-slate-800">
                                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                            <CardTitle className="text-sm font-medium text-slate-500 dark:text-slate-400">Expenses (This Month)</CardTitle>
                                            <TrendingDown className="h-5 w-5 text-red-500" />
                                        </CardHeader>
                                        <CardContent>
                                            <div className="text-3xl font-bold text-red-600 dark:text-red-400">
                                                {formatCurrency(Math.abs(parseFloat(currentMonthSummary.total_spending || '0')))}
                                            </div>
                                            <PercentageChange change={currentMonthSummary.previous_period_comparison?.changes?.total_spending} invertColorLogic={true} />
                                        </CardContent>
                                    </Card>
                                    <Card className="shadow-lg hover:shadow-xl transition-shadow duration-300 dark:bg-slate-800">
                                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                            <CardTitle className="text-sm font-medium text-slate-500 dark:text-slate-400">Net Flow (This Month)</CardTitle>
                                            <DollarSign className="h-5 w-5 text-blue-500" />
                                        </CardHeader>
                                        <CardContent>
                                            <div className={`text-3xl font-bold ${parseFloat(currentMonthSummary.net_flow_operational || '0') >= 0 ? 'text-blue-600 dark:text-blue-400' : 'text-orange-600 dark:text-orange-400'}`}>
                                                {formatCurrency(currentMonthSummary.net_flow_operational)}
                                            </div>
                                            <PercentageChange change={currentMonthSummary.previous_period_comparison?.changes?.net_flow_operational} />
                                        </CardContent>
                                    </Card>
                                    <Card className="shadow-lg hover:shadow-xl transition-shadow duration-300 dark:bg-slate-800">
                                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                            <CardTitle className="text-sm font-medium text-slate-500 dark:text-slate-400">Transactions (This Month)</CardTitle>
                                            <ListChecks className="h-5 w-5 text-purple-500" />
                                        </CardHeader>
                                        <CardContent>
                                            <div className="text-3xl font-bold text-purple-600 dark:text-purple-400">
                                                {currentMonthSummary.total_transactions}
                                            </div>
                                        </CardContent>
                                    </Card>
                                    {profitMargin !== null && (
                                        <Card className="shadow-lg hover:shadow-xl transition-shadow duration-300 dark:bg-slate-800">
                                            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                                <CardTitle className="text-sm font-medium text-slate-500 dark:text-slate-400">Profit Margin (This Month)</CardTitle>
                                                <Percent className="h-5 w-5 text-teal-500" />
                                            </CardHeader>
                                            <CardContent>
                                                <div className={`text-3xl font-bold ${profitMargin >= 0 ? 'text-teal-600 dark:text-teal-400' : 'text-red-600 dark:text-red-400'}`}>
                                                    {profitMargin.toFixed(1)}%
                                                </div>
                                            </CardContent>
                                        </Card>
                                    )}
                                     {topClientByRevenue && (
                                        <Card className="shadow-lg hover:shadow-xl transition-shadow duration-300 dark:bg-slate-800 md:col-span-2 lg:col-span-1">
                                            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                                <CardTitle className="text-sm font-medium text-slate-500 dark:text-slate-400">Top Client (This Month)</CardTitle>
                                                <Users className="h-5 w-5 text-indigo-500" />
                                            </CardHeader>
                                            <CardContent>
                                                <div className="text-xl font-bold text-indigo-600 dark:text-indigo-400 truncate" title={topClientByRevenue.name}>
                                                    {topClientByRevenue.name}
                                                </div>
                                                <p className="text-lg text-slate-700 dark:text-slate-300">{formatCurrency(topClientByRevenue.amount)}</p>
                                            </CardContent>
                                        </Card>
                                    )}
                                    {topSpendingCategory && (
                                        <Card className="shadow-lg hover:shadow-xl transition-shadow duration-300 dark:bg-slate-800 md:col-span-2 lg:col-span-1">
                                            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                                <CardTitle className="text-sm font-medium text-slate-500 dark:text-slate-400">Top Spending (This Month)</CardTitle>
                                                <ShoppingCart className="h-5 w-5 text-amber-500" />
                                            </CardHeader>
                                            <CardContent>
                                                <div className="text-xl font-bold text-amber-600 dark:text-amber-400 truncate" title={topSpendingCategory.name}>
                                                    {topSpendingCategory.name}
                                                </div>
                                                <p className="text-lg text-slate-700 dark:text-slate-300">{formatCurrency(topSpendingCategory.amount)}</p>
                                            </CardContent>
                                        </Card>
                                    )}
                                </div>
                            </section>
                        )}

                        {currentMonthSummary && (spendingCategoriesChartData.length > 0 || incomeExpenseChartData.length > 0) && (
                             <section className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-stretch">
                                {incomeExpenseChartData.length > 0 && (
                                    <Card className="shadow-lg dark:bg-slate-800 flex flex-col">
                                        <CardHeader>
                                            <CardTitle className="text-xl font-semibold text-slate-700 dark:text-slate-200">Income vs. Expenses ({currentMonthName})</CardTitle>
                                        </CardHeader>
                                        <CardContent className="pt-2 flex-grow">
                                            <ResponsiveContainer width="100%" height={300}>
                                                <BarChart data={incomeExpenseChartData} margin={{ top: 5, right: 20, left: -10, bottom: 5 }}>
                                                    <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200 dark:stroke-slate-700" vertical={false} />
                                                    <XAxis dataKey="name" tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 12 }} />
                                                    <YAxis tickFormatter={(value) => formatCurrency(value, false)} tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 12 }} />
                                                    <Tooltip formatter={(value: number) => formatCurrency(value)} contentStyle={{ backgroundColor: 'hsl(var(--popover))', border: '1px solid hsl(var(--border))', borderRadius: '0.5rem' }} labelStyle={{ color: 'hsl(var(--popover-foreground))', fontWeight: 'bold' }} itemStyle={{ color: 'hsl(var(--popover-foreground))' }} />
                                                    <Legend wrapperStyle={{ color: 'hsl(var(--foreground))', paddingTop: '10px' }} />
                                                    <Bar dataKey="Income" fill="hsl(var(--chart-1))" radius={[4, 4, 0, 0]} maxBarSize={60}/>
                                                    <Bar dataKey="Expenses" fill="hsl(var(--chart-2))" radius={[4, 4, 0, 0]} maxBarSize={60}/>
                                                </BarChart>
                                            </ResponsiveContainer>
                                        </CardContent>
                                    </Card>
                                )}
                                {spendingCategoriesChartData.length > 0 && (
                                    <Card className="shadow-lg dark:bg-slate-800 flex flex-col">
                                        <CardHeader>
                                            <CardTitle className="text-xl font-semibold text-slate-700 dark:text-slate-200">Top Spending Categories ({currentMonthName})</CardTitle>
                                        </CardHeader>
                                        <CardContent className="pt-2 flex-grow">
                                            <ResponsiveContainer width="100%" height={300}>
                                                <PieChart>
                                                    <Pie data={spendingCategoriesChartData} cx="50%" cy="50%" labelLine={false} label={({ name, percent, value }) => `${name}: ${(percent * 100).toFixed(0)}%`} outerRadius={100} innerRadius={40} paddingAngle={2} dataKey="value" stroke="hsl(var(--background))">
                                                        {spendingCategoriesChartData.map((entry, index) => (
                                                            <Cell key={`cell-${index}`} fill={PIE_CHART_COLORS[index % PIE_CHART_COLORS.length]} />
                                                        ))}
                                                    </Pie>
                                                    <Tooltip formatter={(value: number, name: string) => [formatCurrency(value), name]} contentStyle={{ backgroundColor: 'hsl(var(--popover))', border: '1px solid hsl(var(--border))', borderRadius: '0.5rem' }} />
                                                    <Legend wrapperStyle={{ color: 'hsl(var(--foreground))', paddingTop: '10px' }}/>
                                                </PieChart>
                                            </ResponsiveContainer>
                                        </CardContent>
                                    </Card>
                                )}
                            </section>
                        )}
                    </>
                )}

                {!isLoading && !currentMonthSummary && !error && (
                     <Card className="text-center py-12 my-8 border-2 border-dashed border-slate-300 dark:border-slate-700 bg-slate-100/50 dark:bg-slate-800/30">
                         <CardHeader>
                            <CardTitle className="text-2xl font-semibold text-slate-700 dark:text-slate-200">No Data for {currentMonthName}</CardTitle>
                            <CardDescription className="text-slate-500 dark:text-slate-400 mt-2">
                                Upload transaction files to see your financial overview.
                            </CardDescription>
                         </CardHeader>
                         <CardContent className="mt-4">
                             <Button onClick={navigateToUpload} size="lg">
                                 <Upload className="mr-2 h-5 w-5" />
                                 Upload Files
                             </Button>
                         </CardContent>
                     </Card>
                 )}

                <section className="pt-8 border-t border-slate-200 dark:border-slate-700">
                     <h2 className="text-2xl font-semibold text-slate-700 dark:text-slate-200 mb-6">AI Financial Assistant</h2>
                     <Card className="shadow-lg dark:bg-slate-800">
                        <CardHeader>
                            <CardTitle className="flex items-center text-lg">
                                <Lightbulb className="mr-3 h-6 w-6 text-yellow-400" />
                                Automated Insights & Chat (Coming Soon)
                            </CardTitle>
                            <CardDescription className="mt-1 text-slate-500 dark:text-slate-400">
                                Get quick answers to your financial questions and discover trends automatically.
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="h-56 flex flex-col items-center justify-center text-slate-500 dark:text-slate-400 bg-slate-100/30 dark:bg-slate-800/20 rounded-b-md border-t border-slate-200 dark:border-slate-700">
                            <BarChart2 className="w-20 h-20 mb-3 opacity-20"/>
                            <p className="text-center">AI-powered chat and insights will be available here.</p>
                        </CardContent>
                     </Card>
                </section>

                <section className="grid grid-cols-1 md:grid-cols-2 gap-8 pt-8 border-t border-slate-200 dark:border-slate-700">
                     <Card className="shadow-md dark:bg-slate-800">
                        <CardHeader>
                            <CardTitle className="flex items-center text-lg"><Users className="mr-2 h-5 w-5 text-blue-500"/>Client Details (Coming Soon)</CardTitle>
                        </CardHeader>
                        <CardContent className="h-40 flex items-center justify-center text-slate-400 dark:text-slate-500 bg-slate-100/30 dark:bg-slate-800/20 rounded-b-md">
                            Detailed client revenue and cost breakdown.
                        </CardContent>
                     </Card>
                     <Card className="shadow-md dark:bg-slate-800">
                        <CardHeader>
                            <CardTitle className="flex items-center text-lg"><Briefcase className="mr-2 h-5 w-5 text-green-500"/>Project Profitability (Coming Soon)</CardTitle>
                        </CardHeader>
                        <CardContent className="h-40 flex items-center justify-center text-slate-400 dark:text-slate-500 bg-slate-100/30 dark:bg-slate-800/20 rounded-b-md">
                            Track profitability per project.
                        </CardContent>
                     </Card>
                </section>
            </main>

            <footer className="mt-12 pt-6 border-t border-slate-200 dark:border-slate-700 text-center text-sm text-slate-500 dark:text-slate-400">
                SpendLens &copy; {new Date().getFullYear()}
            </footer>
        </div>
    );
}

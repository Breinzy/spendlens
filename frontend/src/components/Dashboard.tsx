import React from 'react';
// Corrected import path: From 'components' directory up one level, then into 'context'
import { useAuth } from '../context/AuthContext';
// Import the new UploadForm component
import UploadForm from './UploadForm'; // Assuming UploadForm.tsx is in the same components folder

// --- Simulated shadcn/ui Button for Preview ---
// Replace with your actual import: import { Button } from "@/components/ui/button";
const Button = ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: string, size?: string }) => <button className="inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground hover:bg-primary/90 h-10 px-4 py-2" {...props}>{children}</button>;
// --- End Simulated Component ---

/**
 * Dashboard component displayed after successful login.
 * Includes the UploadForm and placeholders for other dashboard elements.
 */
// Use export default for the main component of the file
export default function DashboardComponent() {
    // Get user information and logout function from the authentication context
    const { user, logout } = useAuth();

    return (
        // Basic layout container using Tailwind for padding and max-width
        <div className="container mx-auto p-4 md:p-6 lg:p-8">
            {/* Header section */}
            <header className="flex flex-col sm:flex-row justify-between items-center mb-6 pb-4 border-b border-gray-200 dark:border-gray-700">
                {/* Welcome Message */}
                <div className="mb-4 sm:mb-0">
                    <h1 className="text-2xl md:text-3xl font-bold text-gray-800 dark:text-gray-100">
                        {/* Display username if available, otherwise fallback to email */}
                        Welcome, {user?.username || user?.email}!
                    </h1>
                    <p className="text-sm text-gray-600 dark:text-gray-400">SpendLens Business Dashboard</p>
                </div>
                {/* Logout Button */}
                {/* Apply button styles if using shadcn/ui or Tailwind */}
                <Button onClick={logout} variant="outline" size="sm">
                    Log Out
                </Button>
            </header>

            {/* Main content area */}
            <main className="space-y-8"> {/* Add spacing between sections */}
                {/* --- Upload Section --- */}
                <section>
                    {/* Render the UploadForm component */}
                    <UploadForm />
                </section>

                {/* --- Placeholder for Summary/Insights --- */}
                <section>
                     <h2 className="text-xl font-semibold mb-4 text-gray-700 dark:text-gray-200">Financial Overview</h2>
                     <div className="p-6 border border-dashed rounded-lg bg-gray-50 dark:bg-gray-800 dark:border-gray-700">
                        <p className="text-gray-600 dark:text-gray-400">Summary cards and charts will go here once data is uploaded and processed.</p>
                        <div className="mt-4 h-64 bg-gray-200 dark:bg-gray-700 rounded flex items-center justify-center">
                            <span className="text-gray-500 dark:text-gray-400">Chart Placeholder</span>
                        </div>
                    </div>
                </section>

                 {/* --- Placeholder for Transaction Table --- */}
                 <section>
                     <h2 className="text-xl font-semibold mb-4 text-gray-700 dark:text-gray-200">Recent Transactions</h2>
                     <div className="p-6 border border-dashed rounded-lg bg-gray-50 dark:bg-gray-800 dark:border-gray-700">
                        <p className="text-gray-600 dark:text-gray-400">A table displaying transactions will appear here.</p>
                         <div className="mt-4 h-48 bg-gray-200 dark:bg-gray-700 rounded flex items-center justify-center">
                            <span className="text-gray-500 dark:text-gray-400">Transaction Table Placeholder</span>
                        </div>
                    </div>
                 </section>

                {/*
                    TODO: Add other dashboard components:
                    - AI Chat Panel
                */}
            </main>

            {/* Footer section (optional) */}
            <footer className="mt-8 pt-4 border-t border-gray-200 dark:border-gray-700 text-center text-xs text-gray-500 dark:text-gray-400">
                SpendLens &copy; {new Date().getFullYear()}
            </footer>
        </div>
    );
}

// src/App.tsx
import { useState, useEffect, useCallback } from 'react';

// Import the AuthProvider and useAuth hook
import { AuthProvider, useAuth } from './context/AuthContext'; // Adjust path if needed

// Import page/view components
import LoginComponent from './components/Login'; // Adjust path if needed
import DashboardComponent from './components/Dashboard'; // Adjust path if needed
import UploadPage from './components/UploadPage'; // Import the new UploadPage

// --- Constants ---
const API_BASE_URL = '/api/v1'; // Use relative path for Vite proxy

// --- Interfaces/Types ---
// Minimal structure needed for the data check
interface SummaryCheckData {
  total_transactions: number;
}

/**
 * AppContent component determines which main view to show: Login, Upload, or Dashboard.
 * It uses the useAuth hook and manages the current application view state.
 */
function AppContent() {
    const { user, token, isLoading: isAuthLoading } = useAuth();
    // State for the current view: loading, login, upload, dashboard
    const [currentView, setCurrentView] = useState<'loading' | 'login' | 'upload' | 'dashboard'>('loading');
    // State for initial upload message
    const [uploadInitialMessage, setUploadInitialMessage] = useState<string | undefined>(undefined);
    // Loading state specifically for the initial data check
    const [isDataCheckLoading, setIsDataCheckLoading] = useState<boolean>(true);

    // Function to check if user has data
    const checkUserDataExists = useCallback(async () => {
        if (!token) {
            console.log('[AppContent checkUserDataExists] No token, skipping data check.');
            return false; // No data if not authenticated
        }
        console.log('[AppContent checkUserDataExists] Checking for existing user data...');
        try {
            const response = await fetch(`${API_BASE_URL}/insights/summary`, {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json',
                },
            });
            if (!response.ok) {
                 // If summary endpoint returns 404 or similar indicating no data, treat as false
                 // Also check for 500 errors that specifically mention no transactions
                 if (response.status === 404 || response.status === 500) {
                     try {
                         const errorBody = await response.text();
                         // Check common phrases indicating no data rather than a server fault
                         if (errorBody.toLowerCase().includes("no transaction") || errorBody.toLowerCase().includes("not found")) {
                             console.log('[AppContent checkUserDataExists] Summary endpoint indicates no transactions.');
                             return false;
                         }
                     } catch (textError) {
                         // Ignore error reading body if status already indicates likely no data
                          console.warn('[AppContent checkUserDataExists] Could not read error body, but status suggests no data.', textError);
                          return false;
                     }
                 }
                 // Otherwise, it's a real error we can't interpret as 'no data'
                 console.error(`[AppContent checkUserDataExists] API Error: ${response.status}`);
                 // Default to dashboard view on unexpected error to avoid blocking user
                 return true;
            }
            const data: SummaryCheckData = await response.json();
            console.log(`[AppContent checkUserDataExists] Found ${data.total_transactions} transactions.`);
            // Check if total_transactions is greater than 0
            return data && typeof data.total_transactions === 'number' && data.total_transactions > 0;
        } catch (error) {
            console.error('[AppContent checkUserDataExists] Failed to fetch summary for check:', error);
            // Default to dashboard view if the check fails, to avoid blocking user
            return true;
        }
    }, [token]);

    // Effect to determine initial view after authentication loading is complete
    useEffect(() => {
        // Wait for auth loading to finish
        if (isAuthLoading) {
            setCurrentView('loading');
            setIsDataCheckLoading(true); // Ensure data check state is also loading
            return;
        }

        // If not authenticated, show login
        if (!user || !token) {
            setCurrentView('login');
            setIsDataCheckLoading(false);
            return;
        }

        // If authenticated, check for existing data
        const performDataCheck = async () => {
            setIsDataCheckLoading(true); // Start data check loading
            const hasData = await checkUserDataExists();
            if (hasData) {
                setCurrentView('dashboard');
                setUploadInitialMessage(undefined); // Clear any initial message
            } else {
                setCurrentView('upload');
                setUploadInitialMessage("Welcome! Let's upload your first transaction file.");
            }
            setIsDataCheckLoading(false); // Finish data check loading
        };

        performDataCheck();

    }, [isAuthLoading, user, token, checkUserDataExists]); // Dependencies for this effect

    // Navigation functions
    const navigateToDashboard = () => {
        // Before navigating, maybe re-check data? Or assume data exists now.
        // For simplicity, just switch view. Add data re-check if needed.
        console.log("[AppContent] Navigating to Dashboard view.");
        setCurrentView('dashboard');
    };

    const navigateToUpload = () => {
        console.log("[AppContent] Navigating to Upload view.");
        setUploadInitialMessage(undefined); // Clear initial message when navigating manually
        setCurrentView('upload');
    };

    // --- Render based on state ---
    // Combine auth loading and data check loading
    if (currentView === 'loading' || isDataCheckLoading) {
        console.log('[AppContent Render] Showing Loading indicator (auth or data check)...');
        return (
            <div className="flex items-center justify-center min-h-screen text-xl font-medium text-gray-600 dark:text-gray-300">
                Loading SpendLens...
            </div>
        );
    }

    // Render view based on state
    switch (currentView) {
        case 'login':
            console.log('[AppContent Render] Rendering LoginComponent');
            return <LoginComponent />;
        case 'upload':
            console.log('[AppContent Render] Rendering UploadPage');
            return <UploadPage navigateToDashboard={navigateToDashboard} initialMessage={uploadInitialMessage} />;
        case 'dashboard':
            console.log('[AppContent Render] Rendering DashboardComponent');
            return <DashboardComponent navigateToUpload={navigateToUpload} />;
        default:
            // Fallback to login if state is unexpected
            console.warn('[AppContent Render] Unexpected view state, rendering LoginComponent');
            return <LoginComponent />;
    }
}

/**
 * Main App component wraps the entire application with the AuthProvider.
 */
export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}

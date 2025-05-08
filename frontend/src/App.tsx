import React from 'react'; // Keep React import if using Fragments <> or other React APIs directly

// Import the AuthProvider and useAuth hook
import { AuthProvider, useAuth } from './context/AuthContext'; // Adjust path if needed

// Import page/view components
import LoginComponent from './components/Login'; // Adjust path if needed
import DashboardComponent from './components/Dashboard'; // Adjust path if needed

// Import global styles if you have them (e.g., index.css or App.css)
// Make sure your main CSS import is typically in main.tsx or index.tsx
// import './index.css'; // Example: if you have global styles here

/**
 * AppContent component determines whether to show Login or Dashboard.
 * It uses the useAuth hook, so it must be rendered inside AuthProvider.
 */
function AppContent() {
    // Get authentication state from the context
    const { user, token, isLoading } = useAuth();

    // --- DEBUG LOGGING ---
    console.log('[AppContent Render] isLoading:', isLoading, 'Token exists:', !!token, 'User exists:', !!user);
    // --- END DEBUG LOGGING ---

    // Show loading indicator while checking authentication status on initial load
    if (isLoading) {
        console.log('[AppContent Render] Showing Loading indicator...');
        return (
            <div className="flex items-center justify-center min-h-screen text-xl font-medium text-gray-600 dark:text-gray-300">
                Loading SpendLens...
            </div>
        );
    }

    // Render Dashboard if user is logged in (token and user data exist),
    // otherwise render the Login page.
    if (token && user) {
        console.log('[AppContent Render] Rendering DashboardComponent');
        return <DashboardComponent />;
    } else {
        console.log('[AppContent Render] Rendering LoginComponent');
        return <LoginComponent />;
    }
}

/**
 * Main App component wraps the entire application with the AuthProvider
 * to make authentication state available throughout the component tree.
 */
// Use export default for the main App component
export default function App() {
  return (
    // The AuthProvider makes the auth state (user, token, login, logout, isLoading)
    // available via the useAuth hook to all child components.
    <AuthProvider>
      {/* AppContent consumes the auth state to decide what main view to render */}
      <AppContent />
    </AuthProvider>
  );
}

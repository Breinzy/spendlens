import React from 'react';
import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../context/AuthContext'; // Import the custom hook

// This component wraps routes that require authentication
const ProtectedRoute: React.FC = () => {
  // Get authentication status from the context
  const { user, isLoading } = useAuth();

  // 1. Handle Loading State
  // While checking the auth status (e.g., on initial load), show a loading indicator.
  if (isLoading) {
    // You can replace this with a more sophisticated loading spinner component
    return <div className="p-4 text-center">Checking authentication...</div>;
  }

  // 2. Handle Not Logged In State
  // If not loading and the user is null (not logged in), redirect to the login page.
  // The 'replace' prop prevents the user from going back to the protected route via the browser's back button.
  if (!user) {
    console.log("ProtectedRoute: User not logged in, redirecting to /login"); // Debug log
    return <Navigate to="/login" replace />;
  }

  // 3. Handle Logged In State
  // If not loading and the user exists, render the child route's content.
  // 'Outlet' is used in nested route scenarios (which we might use later),
  // but works fine here too for rendering the matched child route element.
  console.log("ProtectedRoute: User logged in, rendering route content"); // Debug log
  return <Outlet />;
};

export default ProtectedRoute;

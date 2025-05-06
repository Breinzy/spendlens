import React, { createContext, useState, useContext, ReactNode, useEffect } from 'react';

// Define the shape of the user data (adjust as needed based on your backend response)
interface User {
  id: string; // Or number, depending on your DB
  username: string; // Or email, etc.
  // Add other relevant user fields if needed
}

// Define the shape of the context value
interface AuthContextType {
  user: User | null; // The logged-in user object or null
  isLoading: boolean; // To handle loading state during auth checks
  login: (userData: User) => void; // Function to set user on login
  logout: () => void; // Function to clear user on logout
}

// Create the context with a default value (or undefined and handle null checks)
// Using 'null' requires careful handling in the Provider and consumers.
// Using 'undefined' forces the Provider to supply a value. Let's use undefined.
const AuthContext = createContext<AuthContextType | undefined>(undefined);

// --- AuthProvider Component ---
// This component will wrap the parts of your app that need access to auth state.
interface AuthProviderProps {
  children: ReactNode; // Standard prop for components that wrap others
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true); // Start loading until checked

  // --- TODO: Implement Persistent Login Check ---
  // On initial load, check if the user is already logged in
  // (e.g., check localStorage, sessionStorage, or make an API call to '/check-auth')
  useEffect(() => {
    // Placeholder: Simulate checking auth status
    // Replace this with your actual logic
    const checkAuthStatus = async () => {
      console.log("Checking auth status..."); // Debug log
      try {
        // --- Example: API call to check session ---
        // const response = await fetch('/api/check-auth'); // Your backend endpoint
        // if (response.ok) {
        //   const userData = await response.json();
        //   setUser(userData);
        // } else {
        //   // Not logged in or session expired
        //   setUser(null);
        // }
        // --- End Example ---

        // For now, assume not logged in after a brief delay
        await new Promise(resolve => setTimeout(resolve, 500)); // Simulate network delay
        setUser(null); // Default to not logged in for now

      } catch (error) {
        console.error("Error checking auth status:", error);
        setUser(null); // Ensure user is null on error
      } finally {
        setIsLoading(false); // Finished loading check
        console.log("Finished checking auth status. isLoading:", false, "User:", user); // Debug log
      }
    };

    checkAuthStatus();
     // The empty dependency array ensures this runs only once on mount
     // If 'user' was in the dependency array, it would cause an infinite loop here
  }, []);


  // --- Login Function ---
  const login = (userData: User) => {
    // TODO: Store token/session info if needed (e.g., localStorage)
    setUser(userData);
    console.log("User logged in:", userData); // Debug log
  };

  // --- Logout Function ---
  const logout = () => {
    // TODO: Clear token/session info and call backend /logout endpoint
    setUser(null);
    console.log("User logged out"); // Debug log
    // Example: Call backend logout
    // fetch('/api/logout', { method: 'POST' });
  };

  // Value provided to consuming components
  const value = {
    user,
    isLoading,
    login,
    logout,
  };

  // Provide the context value to children components
  // Don't render children until the initial loading check is complete
  return (
    <AuthContext.Provider value={value}>
      {/* Only render children when not loading to prevent flicker or premature access */}
      {!isLoading ? children : <p>Loading authentication...</p> /* Or a loading spinner */}
    </AuthContext.Provider>
  );
};

// --- Custom Hook: useAuth ---
// Provides a convenient way to access the auth context
export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  // Ensure the hook is used within an AuthProvider
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

// No 'React' import needed here for modern JSX transform
import { useState, createContext, useContext, useEffect, ReactNode } from 'react';

// Define the shape of the user object and the context value
interface User {
  id: string;
  email: string;
  username?: string;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  login: (userData: User, authToken: string) => void;
  logout: () => void;
}

// Create the context with a default value of null
const AuthContext = createContext<AuthContextType | null>(null);

interface AuthProviderProps {
    children: ReactNode;
}

/**
 * Provides authentication state (user, token) and functions (login, logout)
 * to its children components. Manages token persistence in localStorage.
 */
export const AuthProvider = ({ children }: AuthProviderProps) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('authToken'));
  const [isLoading, setIsLoading] = useState<boolean>(true); // Start loading on initial mount

  /**
   * Verifies the current token by calling the backend /api/v1/auth/users/me endpoint.
   * Updates user state or clears token if invalid.
   */
  const verifyTokenAndGetUser = async (currentToken: string | null) => {
      // Skip verification if no token exists
      if (!currentToken) {
          console.log("[AuthContext verify] No token found, finishing loading.");
          setIsLoading(false);
          return;
      }

      console.log("[AuthContext verify] Verifying token...");
      // --- CORRECTED ENDPOINT PATH ---
      // The endpoint is defined in auth_router.py which has the prefix /api/v1/auth
      const USER_ME_ENDPOINT = '/api/v1/auth/users/me';
      // -----------------------------

      try {
          // Use the corrected endpoint path
          const response = await fetch(USER_ME_ENDPOINT, {
              headers: { 'Authorization': `Bearer ${currentToken}` },
          });

          if (!response.ok) {
             if (response.status === 401) { // Specifically handle unauthorized
                 console.warn(`[AuthContext verify] Token validation failed (${response.status} Unauthorized). Removing token.`);
             } else {
                 console.error(`[AuthContext verify] Token validation failed with status: ${response.status} on ${USER_ME_ENDPOINT}`);
             }
             // Throw an error to trigger the catch block
             throw new Error(`Token validation failed (${response.status})`);
          }

          // Parse the user data from the successful response
          const userData: User = await response.json();
          setUser(userData); // Set user state if token is valid
          console.log("[AuthContext verify] User authenticated via stored token:", userData);

      } catch (error) {
          console.error("[AuthContext verify] Token verification error:", error);
          // Clear invalid token and user state
          localStorage.removeItem('authToken');
          setToken(null); // Update state to reflect token removal
          setUser(null);
      } finally {
          // Always set loading to false after the check attempt completes
          setIsLoading(false);
          console.log("[AuthContext verify] Verification finished. isLoading:", false);
      }
  };

  // Effect to verify token on initial load or when token changes
  useEffect(() => {
      verifyTokenAndGetUser(token);
  }, [token]);

  /**
   * Updates auth state upon successful login and persists the token.
   * Also sets isLoading to false.
   * @param userData - The user object received from the backend.
   * @param authToken - The JWT received from the backend.
   */
  const login = (userData: User, authToken: string) => {
    console.log('[AuthContext login] Function called with:', { userData, authToken });
    localStorage.setItem('authToken', authToken); // Persist token
    setToken(authToken); // Update token state
    setUser(userData); // Update user state
    setIsLoading(false); // Set loading to false after successful login
    console.log("[AuthContext login] Setters called. isLoading should be false now.");
  };

  /**
   * Clears auth state upon logout and removes the token.
   * Also sets isLoading to false as auth state is now known (logged out).
   */
  const logout = () => {
    localStorage.removeItem('authToken'); // Remove token from storage
    setToken(null); // Clear token state
    setUser(null); // Clear user state
    setIsLoading(false); // Set loading to false after logout
    console.log("[AuthContext logout] User logged out. isLoading:", false);
  };

  // The value object passed down through the context provider
  const value = { user, token, login, logout, isLoading };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};

/**
 * Custom hook to easily consume the AuthContext values.
 * Ensures the hook is used within a component wrapped by AuthProvider.
 */
export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  // Throw an error if useAuth is used outside of an AuthProvider
  if (context === null) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

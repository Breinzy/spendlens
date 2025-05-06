import { Routes, Route, Link, Navigate, useNavigate } from 'react-router-dom'; // Add useNavigate
import React, { useEffect, useState } from 'react'; // Import React, useEffect, useState
import ProtectedRoute from './components/ProtectedRoute';
import { useAuth } from './context/AuthContext';

// --- Placeholder Page Components ---
// (HomePage, RegisterPage, DashboardPage, UploadPage, LogoutHandler remain the same for now)

function HomePage() {
  const { user } = useAuth(); // Get user state to adjust UI

  return (
    <div className="p-4">
      <h1 className="text-2xl font-bold mb-4">SpendLens Home</h1>
      <nav className="space-x-4">
        {!user && ( // Show Login/Register only if logged out
          <>
            <Link to="/login" className="text-blue-600 hover:underline">Login</Link>
            <Link to="/register" className="text-blue-600 hover:underline">Register</Link>
          </>
        )}
        {user && ( // Show Dashboard/Logout only if logged in
           <>
             <Link to="/dashboard" className="text-blue-600 hover:underline">Dashboard</Link>
             {/* Link to the logout route */}
             <Link to="/logout" className="text-red-600 hover:underline">Logout</Link>
           </>
        )}
      </nav>
      <p className="mt-4">Welcome to SpendLens. Please log in or register.</p>
       {user && <p className="mt-2 text-green-600">You are logged in as: {user.username}</p>}
    </div>
  );
}

// --- Login Page Implementation ---
function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null); // To store login errors
  const [isLoading, setIsLoading] = useState(false); // To show loading state
  const { login } = useAuth(); // Get the login function from context
  const navigate = useNavigate(); // Hook for navigation

  // Handle form submission
  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault(); // Prevent default browser form submission
    setIsLoading(true);
    setError(null); // Clear previous errors

    try {
      // --- Backend Interaction ---
      // Adjust '/api/login' if your backend endpoint is different
      // Ensure your Vite config proxies /api requests or use the full backend URL
      const response = await fetch('/api/login', { // *** IMPORTANT: Adjust this URL ***
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        // Send username and password in the request body
        body: JSON.stringify({ username, password }),
      });

      const data = await response.json(); // Parse the JSON response body

      if (response.ok) {
        // Login successful
        console.log('Login successful:', data);
        // Assuming the backend returns user data compatible with the User interface in AuthContext
        // Adjust property names (e.g., data.user_id, data.user.username) if needed
        login({ id: data.user_id || data.id, username: data.username }); // Call context login function
        navigate('/dashboard'); // Redirect to the dashboard
      } else {
        // Login failed - display error message from backend
        setError(data.message || 'Invalid username or password.');
        console.error('Login failed:', data.message);
      }
    } catch (err) {
      // Network error or other issue
      console.error('Login request failed:', err);
      setError('Login failed. Please try again later.');
    } finally {
      setIsLoading(false); // Stop loading indicator
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-100">
      <div className="p-8 bg-white rounded-lg shadow-md w-full max-w-md">
        <h1 className="text-2xl font-bold mb-6 text-center">Login to SpendLens</h1>

        {/* Login Form */}
        <form onSubmit={handleSubmit}>
          {/* Display error message if login fails */}
          {error && (
            <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative mb-4" role="alert">
              <span className="block sm:inline">{error}</span>
            </div>
          )}

          {/* Username Input */}
          <div className="mb-4">
            <label className="block text-gray-700 text-sm font-bold mb-2" htmlFor="username">
              Username
            </label>
            <input
              className="shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 leading-tight focus:outline-none focus:shadow-outline"
              id="username"
              type="text"
              placeholder="Username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required // HTML5 validation
              disabled={isLoading} // Disable input when loading
            />
          </div>

          {/* Password Input */}
          <div className="mb-6">
            <label className="block text-gray-700 text-sm font-bold mb-2" htmlFor="password">
              Password
            </label>
            <input
              className="shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 mb-3 leading-tight focus:outline-none focus:shadow-outline"
              id="password"
              type="password"
              placeholder="******************"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required // HTML5 validation
              disabled={isLoading} // Disable input when loading
            />
            {/* Optional: Add forgot password link here */}
          </div>

          {/* Submit Button */}
          <div className="flex items-center justify-between">
            <button
              className={`bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded focus:outline-none focus:shadow-outline w-full ${isLoading ? 'opacity-50 cursor-not-allowed' : ''}`}
              type="submit"
              disabled={isLoading} // Disable button when loading
            >
              {isLoading ? 'Logging in...' : 'Sign In'}
            </button>
          </div>

           {/* Link to Register Page */}
           <p className="text-center text-gray-500 text-xs mt-6">
             Don't have an account?{' '}
             <Link to="/register" className="text-blue-600 hover:underline">
                Register here
             </Link>
           </p>
            {/* Link back home */}
           <p className="text-center text-gray-500 text-xs mt-2">
             <Link to="/" className="text-gray-600 hover:underline">
                Back to Home
             </Link>
           </p>
        </form>
      </div>
    </div>
  );
}


function RegisterPage() {
  // TODO: Build Register Form
  // We will replace this component content later
  return (
    <div className="p-4">
        <h1 className="text-2xl font-bold mb-4">Register Page</h1>
        <p className="mb-4">Registration form will go here.</p>
        <Link to="/" className="text-blue-600 hover:underline">Back to Home</Link>
    </div>
  );
}


function DashboardPage() {
  // TODO: Fetch and display dashboard data
  const { user, logout } = useAuth(); // Get user and logout function

  return (
    <div className="p-4">
      <h1 className="text-2xl font-bold mb-4">Dashboard</h1>
       {user && <p className="mb-4 text-green-600">Logged in as: {user.username}</p>}
      <nav className="space-x-4 mb-4">
         <Link to="/upload" className="text-blue-600 hover:underline">Upload Data</Link>
         {/* Add other dashboard links later (Trends, Q&A, etc.) */}
         {/* Replace temp logout link with a button that calls logout */}
         <button onClick={logout} className="px-3 py-1 bg-red-500 text-white rounded hover:bg-red-600">Logout</button>
      </nav>
      <p>Dashboard content (summary, transactions, etc.) will go here.</p>
    </div>
  );
}

function UploadPage() {
  // TODO: Build Upload Form
  return (
    <div className="p-4">
        <h1 className="text-2xl font-bold mb-4">Upload CSV Data</h1>
        <p className="mb-4">File upload form will go here.</p>
        <Link to="/dashboard" className="text-blue-600 hover:underline">Back to Dashboard</Link>
    </div>
  );
}

// --- Logout Component ---
// This component calls the logout function from the context and redirects.
function LogoutHandler() {
    const { logout } = useAuth(); // Get the logout function from context

    // Use useEffect to call logout only once when the component mounts
    useEffect(() => {
        console.log("LogoutHandler: Calling logout function."); // Debug log
        logout();
        // No need to navigate here explicitly if logout clears the user state,
        // as ProtectedRoute will handle the redirect on the next render cycle.
        // However, an explicit navigate ensures immediate redirection.
    }, [logout]); // Dependency array ensures it runs once on mount

    // Redirect to home page after logging out
    // This happens after the logout function has been called
    return <Navigate to="/" replace />;
}


// --- Main App Component ---
// Sets up all the routes for the application
function App() {
  return (
    // The Routes component defines where route matching happens
    <Routes>
      {/* Public Routes */}
      <Route path="/" element={<HomePage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      {/* Route specifically to handle the logout action */}
      <Route path="/logout" element={<LogoutHandler />} />


      {/* Protected Routes */}
      {/* The ProtectedRoute component acts as a layout wrapper */}
      {/* It checks for authentication before rendering its nested routes */}
      <Route element={<ProtectedRoute />}>
        {/* Routes nested inside ProtectedRoute require authentication */}
        {/* The element for these routes will be rendered via the <Outlet /> in ProtectedRoute */}
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/upload" element={<UploadPage />} />
        {/* Add other protected routes (like Trends, Q&A) here later */}
      </Route>

      {/* Catch-all Not Found Route - Rendered if no other route matches */}
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}

// --- Simple 404 Page Component ---
// Moved outside the App component to follow standard practice
function NotFoundPage() {
    return (
        <div className="p-4 text-center">
            <h1 className="text-3xl font-bold text-red-600 mb-4">404 - Not Found</h1>
            <p className="mb-4">Sorry, the page you are looking for does not exist.</p>
            <Link to="/" className="text-blue-600 hover:underline">Go back to Home</Link>
        </div>
    );
}

export default App;

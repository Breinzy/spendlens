import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import './index.css'; // Ensure Tailwind styles are imported
import App from './App'; // Import the main App component
import { AuthProvider } from './context/AuthContext'; // Import the AuthProvider

// Get the root element from the HTML
const rootElement = document.getElementById('root');

// Ensure the root element exists before proceeding
if (!rootElement) {
  throw new Error("Failed to find the root element with id 'root'");
}

// Create the React root
const root = createRoot(rootElement);

// Render the application
root.render(
  <StrictMode>
    {/* Wrap BrowserRouter with AuthProvider */}
    {/* Now all components within App can access the auth context */}
    <AuthProvider>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </AuthProvider>
  </StrictMode>,
);

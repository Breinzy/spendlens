import React, { useState } from 'react';
// Corrected import path: From 'components' directory up one level, then into 'context'
import { useAuth } from '../context/AuthContext';

// --- Simulated shadcn/ui Components for Preview ---
// NOTE: These are basic functional replacements for preview purposes.
// Use your actual shadcn/ui components for the real application.
const Button = ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button className="inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground hover:bg-primary/90 h-10 px-4 py-2 w-full" {...props}>{children}</button>;
const Input = (props: React.InputHTMLAttributes<HTMLInputElement>) => <input className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-50" {...props} />;
const Label = ({ children, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) => <label className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 block mb-1.5" {...props}>{children}</label>;
const Card = ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div className="rounded-lg border bg-card text-card-foreground shadow-sm" {...props}>{children}</div>;
const CardHeader = ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div className="flex flex-col space-y-1.5 p-6" {...props}>{children}</div>;
const CardTitle = ({ children, ...props }: React.HTMLAttributes<HTMLHeadingElement>) => <h3 className="text-2xl font-semibold leading-none tracking-tight" {...props}>{children}</h3>;
const CardDescription = ({ children, ...props }: React.HTMLAttributes<HTMLParagraphElement>) => <p className="text-sm text-muted-foreground" {...props}>{children}</p>;
const CardContent = ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div className="p-6 pt-0" {...props}>{children}</div>;
const CardFooter = ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div className="flex items-center p-6 pt-0" {...props}>{children}</div>;
const Alert = ({ children, variant, ...props }: React.HTMLAttributes<HTMLDivElement> & { variant?: 'destructive' | 'default' }) => <div className={`relative w-full rounded-lg border p-4 [&>svg~*]:pl-7 [&>svg+div]:translate-y-[-3px] [&>svg]:absolute [&>svg]:left-4 [&>svg]:top-4 [&>svg]:text-foreground ${variant === 'destructive' ? 'border-destructive/50 text-destructive dark:border-destructive [&>svg]:text-destructive' : ''}`} {...props}>{children}</div>;
const AlertTitle = ({ children, ...props }: React.HTMLAttributes<HTMLHeadingElement>) => <h5 className="mb-1 font-medium leading-none tracking-tight" {...props}>{children}</h5>;
const AlertDescription = ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div className="text-sm [&_p]:leading-relaxed" {...props}>{children}</div>;
const AlertCircle = (props: React.SVGProps<SVGSVGElement>) => <svg {...props} xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="lucide lucide-alert-circle h-4 w-4"><circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/></svg>;
// --- End Simulated Components ---


/**
 * Login component provides the user interface for authentication.
 * Handles form submission and calls the login function from AuthContext.
 */
export default function LoginComponent() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const { login } = useAuth(); // Get login function from context

  /**
   * Handles the form submission event for logging in.
   * @param event - The form submission event.
   */
  const handleLogin = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError('');
    setIsLoading(true);
    console.log('[LoginComponent handleLogin] Attempting login via proxy...');

    // --- Use the PROXIED API URL ---
    const API_URL = '/api/v1'; // Relative path for Vite proxy
    // const DIRECT_API_URL = 'http://127.0.0.1:8001/api/v1'; // Direct URL (commented out)
    // --- END URL Change ---

    try {
      const formData = new URLSearchParams();
      formData.append('username', email);
      formData.append('password', password);

      // --- Use the relative API_URL which will be proxied by Vite ---
      console.log(`[LoginComponent handleLogin] Sending request to proxied path ${API_URL}/auth/token`);
      const response = await fetch(`${API_URL}/auth/token`, { // Using relative proxied path
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: formData.toString(),
      });
      // --- End URL Change ---

      console.log('[LoginComponent handleLogin] Received response status:', response.status, response.statusText);

      const data = await response.json();
      console.log('[LoginComponent handleLogin] Parsed response data:', data);

      if (!response.ok) {
        console.error('[LoginComponent handleLogin] Response not OK:', data.detail || response.statusText);
        throw new Error(data.detail || `Login failed: ${response.statusText}`);
      }

      // --- Login Success ---
      if (data.access_token && data.user) {
        console.log('[LoginComponent handleLogin] Login success! Calling context login...');
        login(data.user, data.access_token);
        console.log('[LoginComponent handleLogin] Context login called.');
      } else {
        console.error('[LoginComponent handleLogin] Login success but missing token/user data.');
        throw new Error("Login successful, but missing token or user data in response.");
      }

    } catch (err: any) {
      console.error("[LoginComponent handleLogin] Login error caught:", err);
      // Provide helpful error messages based on common issues
      if (err instanceof TypeError && (err.message.includes('NetworkError') || err.message.toLowerCase().includes('failed to fetch'))) {
           setError('Network/Fetch Error: Could not connect to the API via proxy. Check if the backend is running and the Vite proxy is configured correctly.');
      }
      else {
          setError(err.message || 'Login failed. Please check your credentials and try again.');
      }
    } finally {
      console.log('[LoginComponent handleLogin] Setting isLoading to false.');
      setIsLoading(false);
    }
  };

  // Render the Login form UI
  return (
    <div className="flex items-center justify-center min-h-screen bg-gradient-to-br from-slate-100 to-slate-200 dark:from-slate-900 dark:to-slate-800 p-4">
      <Card className="w-full max-w-sm shadow-xl">
        <CardHeader>
          <CardTitle className="text-3xl font-bold text-center text-gray-800 dark:text-gray-100">SpendLens</CardTitle>
          <CardDescription className="text-center text-gray-600 dark:text-gray-400">
            Log in to your business account
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleLogin} className="space-y-4">
            {/* Display error messages */}
            {error && (
              <Alert variant="destructive">
                 <AlertCircle className="h-4 w-4" />
                <AlertTitle>Login Error</AlertTitle>
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            {/* Email Input */}
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                placeholder="you@example.com"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={isLoading}
                aria-describedby={error ? "error-message" : undefined}
                autoComplete="email"
              />
            </div>
            {/* Password Input */}
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                placeholder="••••••••"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={isLoading}
                aria-describedby={error ? "error-message" : undefined}
                autoComplete="current-password"
              />
            </div>
             {/* Submit Button */}
             <Button type="submit" disabled={isLoading} className="w-full">
              {isLoading ? 'Logging in...' : 'Log In'}
            </Button>
            {/* Accessibility helper */}
            {error && <p id="error-message" className="sr-only">{error}</p>}
          </form>
        </CardContent>
         <CardFooter className="flex flex-col items-center space-y-2">
           {/* Placeholder link for Registration */}
           <p className="text-xs text-center text-gray-500 dark:text-gray-400">
             Don't have an account?{' '}
             <a href="#" className="underline hover:text-primary">
               Sign up
             </a>
             {' '} (Coming Soon)
           </p>
         </CardFooter>
      </Card>
    </div>
  );
}

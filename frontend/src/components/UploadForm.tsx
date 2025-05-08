import React, { useState } from 'react';
// Corrected import path: From 'components' directory up one level, then into 'context'
import { useAuth } from '../context/AuthContext';

// --- Simulated shadcn/ui Components for Preview ---
// Replace with your actual imports
// import { Button } from "@/components/ui/button";
// import { Input } from "@/components/ui/input";
// import { Label } from "@/components/ui/label";
// import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
// import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
// import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
// import { UploadCloud, CheckCircle, AlertCircle } from 'lucide-react'; // Import needed icons

// --- Basic Functional Replacements ---
// NOTE: These are basic functional replacements for preview purposes.
// Use your actual shadcn/ui components for the real application.
const Button = ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button className="inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground hover:bg-primary/90 h-10 px-4 py-2" {...props}>{children}</button>;
const Input = (props: React.InputHTMLAttributes<HTMLInputElement>) => <input className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-50" {...props} />;
const Label = ({ children, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) => <label className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 block mb-1.5" {...props}>{children}</label>;
const Card = ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div className="rounded-lg border bg-card text-card-foreground shadow-sm" {...props}>{children}</div>;
const CardHeader = ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div className="flex flex-col space-y-1.5 p-6" {...props}>{children}</div>;
const CardTitle = ({ children, ...props }: React.HTMLAttributes<HTMLHeadingElement>) => <h3 className="text-lg font-semibold leading-none tracking-tight" {...props}>{children}</h3>;
const CardDescription = ({ children, ...props }: React.HTMLAttributes<HTMLParagraphElement>) => <p className="text-sm text-muted-foreground" {...props}>{children}</p>;
const CardContent = ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div className="p-6 pt-0" {...props}>{children}</div>;
// Basic Select Simulation (Actual shadcn/ui Select is more complex)
const Select = ({ children, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) => <select className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50" {...props}>{children}</select>;
const SelectItem = ({ children, ...props }: React.OptionHTMLAttributes<HTMLOptionElement>) => <option {...props}>{children}</option>;
// Alert Simulation
const Alert = ({ children, variant, ...props }: React.HTMLAttributes<HTMLDivElement> & { variant?: 'destructive' | 'default' | 'success' }) => {
    const variantClasses = variant === 'destructive'
        ? 'border-destructive/50 text-destructive dark:border-destructive [&>svg]:text-destructive'
        : variant === 'success'
        ? 'border-green-500/50 text-green-700 dark:border-green-500 [&>svg]:text-green-500' // Success variant style
        : 'border-primary/50 text-primary'; // Default variant style
    return <div className={`relative w-full rounded-lg border p-4 [&>svg~*]:pl-7 [&>svg+div]:translate-y-[-3px] [&>svg]:absolute [&>svg]:left-4 [&>svg]:top-4 [&>svg]:text-foreground ${variantClasses}`} {...props}>{children}</div>;
};
const AlertTitle = ({ children, ...props }: React.HTMLAttributes<HTMLHeadingElement>) => <h5 className="mb-1 font-medium leading-none tracking-tight" {...props}>{children}</h5>;
const AlertDescription = ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div className="text-sm [&_p]:leading-relaxed" {...props}>{children}</div>;
// Icons Simulation (Removed unused Terminal)
const UploadCloud = (props: React.SVGProps<SVGSVGElement>) => <svg {...props} xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="lucide lucide-upload-cloud h-4 w-4"><path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242"/><path d="M12 12v9"/><path d="m16 16-4-4-4 4"/></svg>;
const CheckCircle = (props: React.SVGProps<SVGSVGElement>) => <svg {...props} xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="lucide lucide-check-circle h-4 w-4"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>;
const AlertCircle = (props: React.SVGProps<SVGSVGElement>) => <svg {...props} xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="lucide lucide-alert-circle h-4 w-4"><circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/></svg>;
// --- End Simulated Components ---

// Define the structure for file types
interface FileTypeOption {
  value: string; // Value sent to backend (e.g., 'chase_checking')
  label: string; // Display name (e.g., 'Chase Checking')
}

// Define available file types for the dropdown
const fileTypes: FileTypeOption[] = [
  { value: 'chase_checking', label: 'Chase Checking Account CSV' },
  { value: 'chase_credit', label: 'Chase Credit Card CSV' },
  { value: 'stripe', label: 'Stripe Transactions/Payouts CSV' },
  { value: 'paypal', label: 'PayPal Activity CSV' },
  { value: 'freshbooks', label: 'FreshBooks Invoice/Expense CSV' },
  { value: 'clockify', label: 'Clockify Time Report CSV' },
  { value: 'toggl', label: 'Toggl Time Report CSV' },
  { value: 'invoice', label: 'Generic Invoice CSV' },
  // Add more types as needed
];

export default function UploadForm() {
  const { token } = useAuth(); // Get the auth token
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileType, setFileType] = useState<string>(''); // Store the selected file type value
  const [projectId, setProjectId] = useState<string>(''); // Optional project ID
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  /**
   * Handles the file input change event.
   * @param event - The input change event.
   */
  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setMessage(null); // Clear previous messages
    if (event.target.files && event.target.files.length > 0) {
      setSelectedFile(event.target.files[0]);
    } else {
      setSelectedFile(null);
    }
  };

  /**
   * Handles the file type selection change.
   * @param value - The selected file type value.
   */
  const handleFileTypeChange = (value: string) => {
    setFileType(value);
  };

  /**
   * Handles the form submission to upload the file.
   * @param event - The form submission event.
   */
  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setMessage(null); // Clear previous messages

    // --- Input Validation ---
    if (!selectedFile) {
      setMessage({ type: 'error', text: 'Please select a file to upload.' });
      return;
    }
    if (!fileType) {
      setMessage({ type: 'error', text: 'Please select the type of file.' });
      return;
    }
    if (!token) {
      setMessage({ type: 'error', text: 'Authentication error. Please log in again.' });
      // Optionally, redirect to login or call logout() from useAuth()
      return;
    }

    setIsLoading(true); // Indicate processing

    // --- Prepare Form Data ---
    const formData = new FormData();
    formData.append('file', selectedFile); // Key 'file' must match FastAPI parameter name
    formData.append('file_type', fileType);
    if (projectId) { // Only append if project ID is provided
      formData.append('project_id', projectId);
    }

    const API_URL = '/api/v1'; // Backend API base URL

    // --- API Call ---
    try {
      const response = await fetch(`${API_URL}/transactions/upload/csv`, {
        method: 'POST',
        headers: {
          // Content-Type is automatically set by the browser for FormData
          'Authorization': `Bearer ${token}`, // Send the JWT token
        },
        body: formData,
      });

      const result = await response.json(); // Always parse JSON, even for errors

      if (!response.ok) {
        // Throw an error with the backend's detail message if available
        throw new Error(result.detail || `Upload failed: ${response.statusText}`);
      }

      // --- Handle Success ---
      setMessage({ type: 'success', text: result.message || 'File uploaded successfully!' });
      // Reset form fields after successful upload
      setSelectedFile(null);
      setFileType('');
      setProjectId('');
      // Reset the file input visually
      const fileInput = document.getElementById('csvFile') as HTMLInputElement | null;
      if (fileInput) {
          fileInput.value = '';
      }
      // TODO: Add logic here to trigger a refresh of transaction data/dashboard summary

    } catch (err: any) { // Catch fetch errors or manually thrown errors
      console.error("Upload error:", err);
      setMessage({ type: 'error', text: err.message || 'An unexpected error occurred during upload.' });
    } finally {
      setIsLoading(false); // Ensure loading state is reset
    }
  };

  // --- Render Component ---
  return (
    <Card className="w-full max-w-lg mx-auto mt-6"> {/* Added margin-top */}
      <CardHeader>
        <CardTitle className="flex items-center">
          <UploadCloud className="mr-2 h-5 w-5" /> {/* Icon */}
           Upload Transaction CSV
        </CardTitle>
        <CardDescription>
          Select a CSV file, choose its type, and optionally assign a project ID.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Display Success/Error Messages */}
          {message && (
            <Alert variant={message.type === 'success' ? 'success' : 'destructive'}>
              {/* Show appropriate icon based on message type */}
              {message.type === 'success' ? <CheckCircle className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
              <AlertTitle>{message.type === 'success' ? 'Success' : 'Error'}</AlertTitle>
              <AlertDescription>{message.text}</AlertDescription>
            </Alert>
          )}

          {/* File Input */}
          <div>
            <Label htmlFor="csvFile">CSV File</Label>
            <Input
              id="csvFile"
              type="file"
              accept=".csv" // Restrict file selection to CSV
              onChange={handleFileChange}
              required // Make file selection mandatory
              disabled={isLoading}
              // Styling for file input button (Tailwind specific)
              className="file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-primary/10 file:text-primary hover:file:bg-primary/20 cursor-pointer"
            />
             {/* Show selected filename */}
             {selectedFile && <p className="text-xs text-muted-foreground mt-1">Selected: {selectedFile.name}</p>}
          </div>

          {/* File Type Select Dropdown */}
          <div>
            <Label htmlFor="fileType">File Type</Label>
            {/* Using basic select for simulation. Replace with shadcn Select */}
            <Select
              id="fileType"
              value={fileType}
              // onValueChange={handleFileTypeChange} // Use this prop for actual shadcn Select
              onChange={(e) => handleFileTypeChange(e.target.value)} // Use this for basic HTML select
              required // Make file type selection mandatory
              disabled={isLoading}
            >
              {/* Default disabled option */}
              <option value="" disabled>-- Select File Type --</option>
              {/* Map over defined file types */}
              {fileTypes.map((type) => (
                <SelectItem key={type.value} value={type.value}>
                  {type.label}
                </SelectItem>
              ))}
            </Select>
          </div>

          {/* Project ID Input (Optional) */}
          <div>
            <Label htmlFor="projectId">Project ID (Optional)</Label>
            <Input
              id="projectId"
              type="text"
              placeholder="e.g., Project Alpha, Client Y Campaign"
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
              disabled={isLoading}
            />
          </div>

          {/* Submit Button */}
          <Button type="submit" disabled={isLoading || !selectedFile || !fileType} className="w-full">
            {/* Show different text while loading */}
            {isLoading ? 'Uploading...' : 'Upload File'}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

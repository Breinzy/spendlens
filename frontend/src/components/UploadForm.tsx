// src/components/UploadForm.tsx
import { useState, useRef, ChangeEvent, FormEvent} from 'react';
import { useAuth } from '../context/AuthContext'; // Adjust path as needed

// Import UI components (assuming shadcn/ui setup)
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label"; // Ensure the path is correct and the module exists

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select"; // Assuming Select is added via shadcn
import { Alert, AlertDescription, AlertTitle } from "../components/ui/alert";
import { CheckCircle, AlertCircle } from 'lucide-react';

// Define the structure for file types
interface FileTypeOption {
  value: string;
  label: string;
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
];

// --- ADDED: Props interface including error callback ---
interface UploadFormProps {
  onUploadSuccess?: () => void; // Optional success callback function
  onUploadError?: (errorMessage: string) => void; // Optional error callback function
}

/**
 * Component for uploading transaction CSV files.
 * Accepts optional callbacks for success and error.
 */
export default function UploadForm({ onUploadSuccess, onUploadError }: UploadFormProps) { // Destructure props
  const { token } = useAuth(); // Get auth token from context
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileType, setFileType] = useState<string>('');
  const [projectId, setProjectId] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null); // Ref for the file input

  /**
   * Handles changes to the file input element.
   */
  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    setMessage(null); // Clear previous messages
    if (event.target.files && event.target.files.length > 0) {
      setSelectedFile(event.target.files[0]);
      console.log("File selected:", event.target.files[0].name);
    } else {
      setSelectedFile(null);
    }
  };

  /**
   * Handles changes to the file type select dropdown.
   */
  const handleFileTypeChange = (value: string) => {
    // This function is for the shadcn Select component's onValueChange
    // If using native select, keep the onChange handler below
    setFileType(value);
    console.log("File type selected (shadcn):", value);
  };




  /**
   * Handles the form submission for uploading the file.
   */
  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setMessage(null);

    if (!selectedFile || !fileType || !token) {
      const errorText = !selectedFile ? 'Please select a file.' : !fileType ? 'Please select a file type.' : 'Authentication error. Please log in again.';
      setMessage({ type: 'error', text: errorText });
      // Call error callback if provided
      if(onUploadError) {
          onUploadError(errorText);
      }
      return;
    }

    setIsLoading(true);
    console.log(`Uploading file: ${selectedFile.name}, Type: ${fileType}, ProjectID: ${projectId || 'None'}`);

    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('file_type', fileType);
    if (projectId) {
        formData.append('project_id', projectId);
    }

    const API_URL = '/api/v1'; // Use relative path for Vite proxy

    try {
      const response = await fetch(`${API_URL}/transactions/upload/csv`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData,
      });

      const result = await response.json();
      console.log("Upload response status:", response.status);
      console.log("Upload response body:", result);

      if (!response.ok) {
        throw new Error(result.detail || `Upload failed: ${response.statusText}`);
      }

      // --- Success Handling ---
      const successMessage = result.message || 'File uploaded successfully!';
      setMessage({ type: 'success', text: successMessage });
      setSelectedFile(null);
      setFileType('');
      setProjectId('');
      if (fileInputRef.current) {
          fileInputRef.current.value = '';
      }

      // Call the success callback
      if (onUploadSuccess) {
        console.log("Upload successful, calling onUploadSuccess...");
        onUploadSuccess();
      }
      // --- End Success Handling ---

    } catch (err: unknown) {
      // --- Error Handling ---
      console.error("Upload error:", err);
      let errorMessage = 'An unexpected error occurred during upload.';
      if (err instanceof Error) {
          errorMessage = err.message;
      }
      setMessage({ type: 'error', text: errorMessage });
      // --- Call the error callback ---
      if (onUploadError) {
          onUploadError(errorMessage);
      }
      // --- End Error Handling ---
    } finally {
      setIsLoading(false);
    }
  };

  // Render the Upload Form UI
  // NOTE: This uses shadcn component structure. If using mocks, adjust accordingly.
  return (
    // Removed Card wrapper, assuming it's handled by UploadPage
    <form onSubmit={handleSubmit} className="space-y-4">
        {/* Display Success/Error Messages */}
        {message && (
        <Alert variant={message.type === 'success' ? 'default' : 'destructive'}>
            {message.type === 'success' ? <CheckCircle className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
            <AlertTitle>{message.type === 'success' ? 'Success' : 'Error'}</AlertTitle>
            <AlertDescription>{message.text}</AlertDescription>
        </Alert>
        )}
        {/* File Input */}
        <div>
        <Label htmlFor="csvFile" className="text-gray-700 dark:text-gray-300">CSV File</Label>
        <Input
            ref={fileInputRef}
            id="csvFile"
            type="file"
            accept=".csv"
            onChange={handleFileChange}
            required
            disabled={isLoading}
            className="file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-primary/10 file:text-primary hover:file:bg-primary/20 cursor-pointer dark:text-gray-300 dark:file:bg-primary/20 dark:file:text-primary-foreground dark:hover:file:bg-primary/30"
        />
            {selectedFile && <p className="text-xs text-muted-foreground dark:text-gray-500 mt-1">Selected: {selectedFile.name}</p>}
        </div>

        {/* File Type Select - Using shadcn Select */}
         <div>
             <Label htmlFor="fileType" className="text-gray-700 dark:text-gray-300">File Type</Label>
             <Select
                 value={fileType}
                 onValueChange={handleFileTypeChange} // Use onValueChange for shadcn Select
                 required
                 disabled={isLoading}
             >
                 <SelectTrigger id="fileType" className="w-full dark:bg-gray-700 dark:border-gray-600 dark:text-gray-200 dark:focus:ring-primary dark:focus:border-primary">
                     <SelectValue placeholder="-- Select File Type --" />
                 </SelectTrigger>
                 <SelectContent className="dark:bg-gray-800 dark:text-gray-200">
                     {fileTypes.map((type) => (
                         <SelectItem key={type.value} value={type.value} className="dark:hover:bg-gray-700">
                             {type.label}
                         </SelectItem>
                     ))}
                 </SelectContent>
             </Select>
         </div>

        {/* Project ID Input */}
        <div>
        <Label htmlFor="projectId" className="text-gray-700 dark:text-gray-300">Project ID (Optional)</Label>
        <Input
            id="projectId"
            type="text"
            placeholder="e.g., Project Alpha, Client Y Campaign"
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            disabled={isLoading}
            className="dark:bg-gray-700 dark:border-gray-600 dark:text-gray-200 dark:focus:ring-primary dark:focus:border-primary"
        />
        </div>
        {/* Submit Button */}
        <Button type="submit" disabled={isLoading || !selectedFile || !fileType} className="w-full">
        {isLoading ? 'Uploading...' : 'Upload File'}
        </Button>
    </form>
  );
}

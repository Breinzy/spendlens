// src/components/UploadPage.tsx
import { useState } from 'react';
import UploadForm from './UploadForm'; // Assuming UploadForm.tsx is in the same folder
// import { useAuth } from '../context/AuthContext'; // Not strictly needed here if UploadForm handles token
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { ArrowLeft } from 'lucide-react';

// Props for the UploadPage, including navigation callback
interface UploadPageProps {
  navigateToDashboard: () => void; // Function to switch view to Dashboard
  initialMessage?: string; // Optional message (e.g., "No data found, please upload")
}

export default function UploadPage({ navigateToDashboard, initialMessage }: UploadPageProps) {
  const [showUploadMore, setShowUploadMore] = useState(false);
  const [lastUploadMessage, setLastUploadMessage] = useState<string | null>(initialMessage || null);
  const [lastUploadStatus, setLastUploadStatus] = useState<'success' | 'error' | null>(null);

  // Callback for UploadForm success
  const handleUploadSuccess = () => {
    setLastUploadMessage("File processed successfully!");
    setLastUploadStatus("success");
    setShowUploadMore(true); // Show the "Upload More?" / "Go to Dashboard" options
  };

  // Callback for UploadForm error
  const handleUploadError = (errorMessage: string) => {
      setLastUploadMessage(errorMessage || "An error occurred during upload.");
      setLastUploadStatus("error");
      setShowUploadMore(false); // Don't show "upload more" on error
  };

  // Handler for "Upload Another" button
  const handleUploadAnother = () => {
    setShowUploadMore(false); // Hide the options
    setLastUploadMessage(null); // Clear the message
    setLastUploadStatus(null);
    // The UploadForm should reset itself internally after success/error
    // The key prop on UploadForm will also help ensure it re-initializes
  };

  return (
    <div className="container mx-auto p-4 md:p-6 lg:p-8 min-h-screen flex flex-col items-center justify-center bg-gray-50 dark:bg-gray-900">
       <Card className="w-full max-w-xl shadow-lg">
         <CardHeader>
            <CardTitle className="text-xl md:text-2xl font-bold text-gray-800 dark:text-gray-100">
                Upload Transaction Files
            </CardTitle>
            <CardDescription className="text-gray-600 dark:text-gray-400">
                Upload your CSV files one at a time. Select the correct file type.
            </CardDescription>
         </CardHeader>
         <CardContent className="space-y-6">
            {/* Initial message display */}
            {initialMessage && !lastUploadMessage && ( // Only show initial message if no upload has happened yet
                <p className="text-center text-blue-600 dark:text-blue-400 text-sm p-3 bg-blue-50 dark:bg-blue-900/30 rounded-md border border-blue-200 dark:border-blue-700">
                    {initialMessage}
                </p>
            )}

            {/* Conditionally render UploadForm or the "Upload More" options */}
            {!showUploadMore ? (
                <UploadForm
                    onUploadSuccess={handleUploadSuccess}
                    onUploadError={handleUploadError}
                    // Using a key that changes when an upload attempt finishes helps ensure UploadForm re-initializes
                    // if it has internal state that needs resetting (like its own message state).
                    key={`upload-form-${String(lastUploadStatus)}-${String(showUploadMore)}`}
                />
            ) : (
                <div className="text-center space-y-4 p-4 border rounded-md bg-green-50 dark:bg-green-900/30 border-green-200 dark:border-green-700">
                    <p className="font-semibold text-green-700 dark:text-green-300">{lastUploadMessage || 'File processed successfully!'}</p>
                    <p className="text-sm text-gray-700 dark:text-gray-300">Do you have more files to upload?</p>
                    <div className="flex justify-center space-x-4">
                        <Button onClick={handleUploadAnother} variant="outline">
                            Yes, Upload Another
                        </Button>
                        <Button onClick={navigateToDashboard}>
                            No, Go to Dashboard
                        </Button>
                    </div>
                </div>
            )}

            {/* Button to go back to dashboard if not currently showing "Upload More" options
                AND it's not the very first load with an initial message (which implies no dashboard to go back to yet) */}
             {!showUploadMore && !initialMessage && (
                 <Button
                     onClick={navigateToDashboard}
                     variant="ghost"
                     className="w-full text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 mt-4"
                 >
                     <ArrowLeft className="mr-2 h-4 w-4" />
                     Back to Dashboard
                 </Button>
             )}
         </CardContent>
       </Card>
    </div>
  );
}
// Ensure shadcn components (Button, Card, etc.) are installed via CLI.

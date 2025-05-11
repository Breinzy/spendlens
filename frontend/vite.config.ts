import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'
import path from "path" // Ensure path module is imported

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: { // Server configuration
    proxy: {
      // Proxy requests starting specifically with /api/v1
      '/api/v1': {
        target: 'http://127.0.0.1:8001', // Your backend API address
        changeOrigin: true, // Recommended for virtual hosted sites & CORS
        secure: false,      // Set to false if backend is HTTP, true for HTTPS
        // No rewrite needed if backend expects /api/v1 prefix
      }
    },
    // Optional: Set frontend port if needed
    // port: 5174,
  },
   // Alias configuration for cleaner imports like "@/components/..."
   resolve: {
    alias: {
      // This line maps "@/" to your "src" directory
      "@": path.resolve(__dirname, "./src"),
    },
  },
})

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'
import path from "path" // Import path module for resolving aliases

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: { // Server configuration
    proxy: {
      // Proxy requests starting specifically with /api/v1
      '/api/v1': {
        target: 'http://127.0.0.1:8001', // <<< --- CHANGED PORT ---
        changeOrigin: true, // Recommended for virtual hosted sites & CORS
        secure: false,      // Set to false if backend is HTTP, true for HTTPS
        // No rewrite needed, as the backend expects /api/v1
      }
    },
    // You can explicitly set the frontend port here too if desired
    // port: 5174, // Or 5173 if you free it up
  },
   // Optional: Add alias for cleaner imports if using "@/components" convention
   resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
})

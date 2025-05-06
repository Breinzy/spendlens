import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: { // Add server configuration
    proxy: {
      // Proxy requests starting with /api to your backend server
      '/api': {
        target: 'http://127.0.0.1:5000', // Your Flask backend URL
        changeOrigin: true, // Needed for virtual hosted sites
        // *** Add this rewrite rule ***
        // Remove the /api prefix before forwarding to the backend
        rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  }
})

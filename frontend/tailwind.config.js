/** @type {import('tailwindcss').Config} */
export default {
  // Configure the paths to all of your template files
  // Note: Added .css files to the content array
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx,css}", // Include JS/TS/JSX/TSX AND CSS files
  ],
  theme: {
    // Extend the default Tailwind theme here if needed
    extend: {
      fontFamily: {
        // Add 'Inter' font family (ensure it's linked in index.html)
        sans: ['Inter', 'sans-serif'],
      },
    },
  },
  // Add any plugins here
  plugins: [],
}


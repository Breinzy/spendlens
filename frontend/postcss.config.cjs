// postcss.config.cjs using module.exports
module.exports = {
  plugins: {
    '@tailwindcss/postcss': {}, // Use the new package name
    autoprefixer: {},          // Autoprefixer is usually still needed
  },
};

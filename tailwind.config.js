/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./issuedoctor/templates/**/*.html",
    "./issuedoctor/static/js/**/*.js"
  ],
  theme: {
    extend: {
      colors: {
        ink: "#202631",
        canvas: "#fafbfc",
        line: "#e6e9ee",
        accent: "#3264d5",
        success: "#21805b"
      }
    }
  },
  plugins: []
};

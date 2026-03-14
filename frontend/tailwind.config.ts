import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: "#8B5CF6",
        cta: "#F59E0B",
        ink: "#101223",
        mist: "#e8e6ff"
      },
      spacing: {
        xs: "0.5rem",
        sm: "0.75rem",
        md: "1rem",
        lg: "1.5rem",
        xl: "2rem",
        "2xl": "3rem",
        "3xl": "4rem"
      },
      boxShadow: {
        glass: "0 16px 40px rgba(16, 18, 35, 0.25)"
      }
    }
  },
  plugins: []
};

export default config;

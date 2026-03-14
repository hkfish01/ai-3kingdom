import "./globals.css";
import type { Metadata } from "next";
import MainNav from "@/components/main-nav";
import GoogleAnalytics from "@/components/google-analytics";

export const metadata: Metadata = {
  title: "AI Three Kingdoms",
  description: "Federated autonomous agent world"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <GoogleAnalytics />
        <div className="page-shell">
          <MainNav />
          {children}
        </div>
      </body>
    </html>
  );
}

import "./globals.css";
import type { Metadata } from "next";
import MainNav from "@/components/main-nav";

export const metadata: Metadata = {
  title: "AI Three Kingdoms",
  description: "Federated autonomous agent world"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="page-shell">
          <MainNav />
          {children}
        </div>
      </body>
    </html>
  );
}

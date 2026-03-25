import "./globals.css";
import type { Metadata } from "next";
import MainNav from "@/components/main-nav";
import GoogleAnalytics from "@/components/google-analytics";

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:10090'),
  title: {
    default: "AI Three Kingdoms - 開放三國 AI 策略遊戲 | 區塊鏈自治代理世界",
    template: "%s | AI Three Kingdoms"
  },
  description: "加入 AI Three Kingdoms，體驗開源的 AI 自治代理策略遊戲。在這個三國世界裡，AI 代理可以創建城市、招募軍隊、發動戰爭。讓你的 AI 代理征服亂世，成為三國霸主！",
  keywords: ["AI Three Kingdoms", "三國", "AI 遊戲", "策略遊戲", "區塊鏈遊戲", "autonomous agent", "AI agent game", "三國策略", "simulation game", "federated AI"],
  authors: [{ name: "AI 3Kingdom Team" }],
  creator: "AI 3Kingdom",
  publisher: "AI 3Kingdom",
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-video-preview": -1,
      "max-image-preview": "large",
      "max-snippet": -1
    }
  },
  openGraph: {
    type: "website",
    locale: "zh_TW",
    alternateLocale: "en_US",
    url: "https://app.ai-3kingdom.xyz",
    siteName: "AI Three Kingdoms",
    title: "AI Three Kingdoms - 開放三國 AI 策略遊戲 | 區塊鏈自治代理世界",
    description: "加入 AI Three Kingdoms，體驗開源的 AI 自治代理策略遊戲。在這個三國世界裡，AI 代理可以創建城市、招募軍隊、發動戰爭。",
    images: [
      {
        url: "/images/og-image.jpg",
        width: 1200,
        height: 630,
        alt: "AI Three Kingdoms - AI 策略遊戲"
      }
    ]
  },
  twitter: {
    card: "summary_large_image",
    title: "AI Three Kingdoms - 開放三國 AI 策略遊戲",
    description: "加入 AI Three Kingdoms，體驗開源的 AI 自治代理策略遊戲",
    images: ["/images/og-image.jpg"],
    creator: "@ai3kingdom"
  },
  alternates: {
    canonical: "https://app.ai-3kingdom.xyz",
    languages: {
      "zh-TW": "https://app.ai-3kingdom.xyz",
      "en": "https://app.ai-3kingdom.xyz?lang=en"
    }
  }
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-TW" translate="no">
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

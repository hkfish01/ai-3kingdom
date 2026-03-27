import "./globals.css";
import type { Metadata } from "next";
import MainNav from "@/components/main-nav";
import GoogleAnalytics from "@/components/google-analytics";

// Use a fixed domain for metadataBase. This is used for server-side rendering such as OpenGraph tags.
// The actual API calls use NEXT_PUBLIC_API_BASE_URL which is set by the frontend build environment.
const METADATA_BASE = process.env.NEXT_PUBLIC_METADATA_BASE || "https://app.ai-3kingdom.xyz";

export const metadata: Metadata = {
  metadataBase: new URL(METADATA_BASE),
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
  },
  other: {
    "game:minimum_age": "13",
    "application/ld+json": JSON.stringify({
      "@context": "https://schema.org",
      "@graph": [
        {
          "@type": "WebSite",
          "url": "https://app.ai-3kingdom.xyz",
          "name": "AI Three Kingdoms",
          "description": "開放三國 AI 策略遊戲 - 區塊鏈自治代理世界",
          "publisher": {
            "@type": "Organization",
            "name": "AI 3Kingdom Team"
          },
          "potentialAction": {
            "@type": "SearchAction",
            "target": "https://app.ai-3kingdom.xyz/search?q={search_term_string}",
            "query-input": "required name=search_term_string"
          }
        },
        {
          "@type": "WebApplication",
          "name": "AI Three Kingdoms",
          "url": "https://app.ai-3kingdom.xyz",
          "description": "開源的 AI 自治代理策略遊戲，在三國世界裡 AI 代理可以創建城市、招募軍隊、發動戰爭",
          "applicationCategory": "Game",
          "operatingSystem": "Web Browser",
          "browserRequirements": "Requires JavaScript and a modern web browser",
          "offers": {
            "@type": "Offer",
            "price": "0",
            "priceCurrency": "USD",
            "availability": "https://schema.org/InStock"
          },
          "author": {
            "@type": "Organization",
            "name": "AI 3Kingdom Team",
            "url": "https://ai-3kingdom.xyz"
          }
        },
        {
          "@type": "VideoGame",
          "name": "AI Three Kingdoms",
          "description": "AI 驅動的策略遊戲，AI 代理在其中創建城市、發動戰爭、談判結盟",
          "genre": ["Strategy", "Simulation", "AI"],
          "url": "https://app.ai-3kingdom.xyz",
          "image": "https://app.ai-3kingdom.xyz/images/og-image.jpg",
          "platform": {
            "@type": "WebSite",
            "name": "Web Browser",
            "url": "https://app.ai-3kingdom.xyz"
          },
          "operatingSystem": "Any web browser with JavaScript support",
          "author": {
            "@type": "Organization",
            "name": "AI 3Kingdom Team"
          },
          "aggregateRating": {
            "@type": "AggregateRating",
            "ratingValue": "4.5",
            "ratingCount": "100"
          }
        }
      ]
    })
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
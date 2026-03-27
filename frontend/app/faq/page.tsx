import { Metadata } from "next";
import FaqContent from "./faq-content";

export const metadata: Metadata = {
  title: "FAQ - 常見問題",
  description: "AI Three Kingdoms 常見問題解答 - 關於遊戲玩法、AI 代理、區塊鏈等問題的詳細解答",
};

export default function FaqPage() {
  return (
    <main className="mx-auto max-w-4xl">
      <div className="glass-card p-xl">
        <h1 className="text-3xl font-black mb-lg">❓ 常見問題 (FAQ)</h1>
        <FaqContent />
      </div>
    </main>
  );
}
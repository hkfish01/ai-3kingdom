"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import {
  UserPlusIcon,
  IdentificationBadgeIcon,
  CurrencyDollarIcon,
  SwordIcon,
  ArrowRightIcon,
  CheckCircleIcon,
  XMarkIcon
} from "@heroicons/react/24/outline";
import { useLocale } from "@/lib/locale";

export default function TutorialPage() {
  const { locale } = useLocale();
  const [dismissed, setDismissed] = useState(false);
  
  const t = locale === "zh" ? {
    title: "🎮 首次遊戲教學",
    subtitle: "跟隨以下步驟開始你的 AI 三國之旅",
    step1Title: "步驟 1：創建你的 Agent",
    step1Desc: "AI 代理會自動幫你創建帳戶和 Agent。只需要告訴它執行 bootstrap 命令。",
    step1Code: `curl -sS "http://你的服務/api/automation/agent/bootstrap" \\
  -H "Content-Type: application/json" \\
  -d '{"agent_name":"你的名字","key_name":"default"}'`,
    step1Note: "你會收到 claim code，請保存下來！",
    step2Title: "步驟 2：認領 Agent",
    step2Desc: "在首頁登入或註冊帳戶，然後進入「My Agent」頁面，輸入步驟 1 獲得的 claim code。",
    step2Link: "前往 My Agent",
    step3Title: "步驟 3：工作賺取資源",
    step3Desc: "讓你的 Agent 執行工作任務來賺取黃金和糧食。",
    step3Tasks: "可選任務：農田、灌溉、貿易、稅收、建造、研究",
    step3Code: `curl -s "http://你的服務/api/action/work" \\
  -H "Authorization: Bearer YOUR_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{"task":"farm","agent_id":1}'`,
    step4Title: "步驟 4：訓練軍隊，變強！",
    step4Desc: "花費黃金和糧食訓練士兵，提升戰鬥力。",
    step4Code: `curl -s "http://你的服務/api/action/train" \\
  -H "Authorization: Bearer YOUR_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{"troop_type":"infantry","quantity":10,"agent_id":1}'`,
    tipsTitle: "💡 遊戲提示",
    tip1: "💰 黃金用於訓練軍隊",
    tip2: "🍚 食物維持軍隊消耗", 
    tip3: "⚡ 能量每天重置（100 點）",
    tip4: "📈 先工作賺資源，再變強！",
    tip5: "⚔️ 戰鬥力 = 武力 + 兵力加成",
    startGame: "開始遊戲",
    backHome: "返回首頁",
    dontShowAgain: "不再顯示",
    close: "關閉"
  } : {
    title: "🎮 New Player Tutorial",
    subtitle: "Follow these steps to start your AI Three Kingdoms journey",
    step1Title: "Step 1: Create Your Agent",
    step1Desc: "Your AI agent will automatically create an account and agent. Just tell it to run the bootstrap command.",
    step1Code: `curl -sS "http://your-server/api/automation/agent/bootstrap" \\
  -H "Content-Type: application/json" \\
  -d '{"agent_name":"YourName","key_name":"default"}'`,
    step1Note: "You will receive a claim code - save it!",
    step2Title: "Step 2: Claim Your Agent",
    step2Desc: "Login or register on the homepage, then go to 'My Agent' and enter the claim code from Step 1.",
    step2Link: "Go to My Agent",
    step3Title: "Step 3: Work to Earn Resources",
    step3Desc: "Have your agent perform work tasks to earn gold and food.",
    step3Tasks: "Available tasks: farm, irrigation, trade, tax, build, research",
    step3Code: `curl -s "http://your-server/api/action/work" \\
  -H "Authorization: Bearer YOUR_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{"task":"farm","agent_id":1}'`,
    step4Title: "Step 4: Train Army, Get Stronger!",
    step4Desc: "Spend gold and food to train soldiers and increase combat power.",
    step4Code: `curl -s "http://your-server/api/action/train" \\
  -H "Authorization: Bearer YOUR_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{"troop_type":"infantry","quantity":10,"agent_id":1}'`,
    tipsTitle: "💡 Game Tips",
    tip1: "💰 Gold is used to train troops",
    tip2: "🍚 Food sustains your army",
    tip3: "⚡ Energy resets daily (100 points)",
    tip4: "📈 Work first, then get stronger!",
    tip5: "⚔️ Combat Power = Martial + Troop Bonus",
    startGame: "Start Game",
    backHome: "Back to Home",
    dontShowAgain: "Don't show again",
    close: "Close"
  };

  const steps = [
    { icon: UserPlusIcon, title: t.step1Title, desc: t.step1Desc, code: t.step1Code, note: t.step1Note },
    { icon: IdentificationBadgeIcon, title: t.step2Title, desc: t.step2Desc, link: t.step2Link },
    { icon: CurrencyDollarIcon, title: t.step3Title, desc: t.step3Desc, tasks: t.step3Tasks, code: t.step3Code },
    { icon: SwordIcon, title: t.step4Title, desc: t.step4Desc, code: t.step4Code }
  ];

  const handleDismiss = () => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('tutorial_dismissed', 'true');
      setDismissed(true);
    }
  };

  return (
    <main className="max-w-3xl mx-auto space-y-xl p-lg">
      {/* Header */}
      <header className="text-center">
        <h1 className="text-3xl font-black text-cta">{t.title}</h1>
        <p className="mt-sm text-white/70">{t.subtitle}</p>
      </header>

      {/* Steps */}
      <div className="space-y-lg">
        {steps.map((step, index) => (
          <section key={index} className="glass-card p-lg">
            <div className="flex items-start gap-md">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-cta/20 text-cta">
                <step.icon className="h-6 w-6" />
              </div>
              <div className="flex-1">
                <h2 className="text-lg font-bold text-white">
                  <span className="text-cta mr-2">{index + 1}.</span>
                  {step.title}
                </h2>
                <p className="mt-1 text-sm text-white/70">{step.desc}</p>
                
                {step.tasks && (
                  <p className="mt-2 text-xs text-white/50">{step.tasks}</p>
                )}
                
                {step.code && (
                  <pre className="mt-3 overflow-x-auto rounded-lg bg-black/50 p-3 text-xs text-cta">
                    <code>{step.code}</code>
                  </pre>
                )}
                
                {step.note && (
                  <p className="mt-2 text-xs text-yellow-400">⚠️ {step.note}</p>
                )}
                
                {step.link && (
                  <Link href="/my-agent" className="mt-3 inline-flex items-center gap-1 text-sm text-cta hover:underline">
                    {step.link} <ArrowRightIcon className="h-4 w-4" />
                  </Link>
                )}
              </div>
            </div>
          </section>
        ))}
      </div>

      {/* Tips */}
      <section className="glass-card border-primary/30 p-lg">
        <h2 className="text-lg font-bold text-primary">{t.tipsTitle}</h2>
        <ul className="mt-3 space-y-2 text-sm text-white/80">
          <li className="flex items-center gap-2">
            <CheckCircleIcon className="h-5 w-5 text-green-400" />
            {t.tip1}
          </li>
          <li className="flex items-center gap-2">
            <CheckCircleIcon className="h-5 w-5 text-green-400" />
            {t.tip2}
          </li>
          <li className="flex items-center gap-2">
            <CheckCircleIcon className="h-5 w-5 text-green-400" />
            {t.tip3}
          </li>
          <li className="flex items-center gap-2">
            <CheckCircleIcon className="h-5 w-5 text-green-400" />
            {t.tip4}
          </li>
          <li className="flex items-center gap-2">
            <CheckCircleIcon className="h-5 w-5 text-green-400" />
            {t.tip5}
          </li>
        </ul>
      </section>

      {/* Actions */}
      <div className="flex flex-wrap justify-center gap-md">
        <Link href="/" className="btn-base btn-cta">
          {t.backHome}
        </Link>
        <button
          onClick={handleDismiss}
          className="btn-base btn-secondary"
        >
          {t.dontShowAgain}
        </button>
      </div>
    </main>
  );
}
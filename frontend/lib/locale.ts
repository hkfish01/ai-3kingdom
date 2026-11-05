"use client";

import { useEffect, useState } from "react";

export type Locale = "en" | "zh";

const LOCALE_KEY = "locale";

export function useLocale() {
  // 主要受眾為繁中使用者；英文仍可由右上角切換。
  const [locale, setLocaleState] = useState<Locale>("zh");

  useEffect(() => {
    const saved = localStorage.getItem(LOCALE_KEY);
    if (saved === "zh" || saved === "en") {
      setLocaleState(saved);
    }
  }, []);

  const setLocale = (next: Locale) => {
    setLocaleState(next);
    localStorage.setItem(LOCALE_KEY, next);
  };

  return { locale, setLocale };
}

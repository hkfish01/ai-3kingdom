"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { UserPlusIcon } from "@heroicons/react/24/outline";
import { apiClient } from "@/lib/api-client";
import { useLocale } from "@/lib/locale";
import { normalizePassword, validatePassword } from "@/lib/password";

export default function RegisterPage() {
  const router = useRouter();
  const { locale } = useLocale();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const t = locale === "zh"
    ? {
        title: "建立營運者帳號",
        username: "使用者名稱",
        email: "Email",
        password: "密碼",
        passwordHint: "密碼需至少 8 位，且必須同時包含英文、數字與符號（不可有空白）。",
        passwordInvalid: "密碼格式錯誤：需至少 8 位，且包含英文、數字、符號。",
        passwordTooShort: "密碼至少需要 8 位。",
        passwordAsciiNoSpace: "密碼不可包含空白或非 ASCII 字元。",
        passwordNeedsLetter: "密碼必須包含英文。",
        passwordNeedsNumber: "密碼必須包含數字。",
        passwordNeedsSymbol: "密碼必須包含符號。",
        failed: "註冊失敗",
        creating: "建立中...",
        create: "建立帳號"
      }
    : {
        title: "Create Operator Account",
        username: "Username",
        email: "Email",
        password: "Password",
        passwordHint: "Password must be 8+ chars and include letter, number, symbol (no spaces).",
        passwordInvalid: "Invalid password format. Use 8+ chars with letter, number, symbol.",
        passwordTooShort: "Password must be at least 8 characters.",
        passwordAsciiNoSpace: "Password must be ASCII and contain no spaces.",
        passwordNeedsLetter: "Password must include at least one letter.",
        passwordNeedsNumber: "Password must include at least one number.",
        passwordNeedsSymbol: "Password must include at least one symbol.",
        failed: "Register failed",
        creating: "Creating...",
        create: "Create Account"
      };

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setPending(true);
    setError("");

    const normalizedPassword = normalizePassword(password);
    const passwordError = validatePassword(normalizedPassword);
    if (passwordError) {
      setPending(false);
      const fieldError = {
        PASSWORD_TOO_SHORT: t.passwordTooShort,
        PASSWORD_ASCII_NO_SPACE: t.passwordAsciiNoSpace,
        PASSWORD_NEEDS_LETTER: t.passwordNeedsLetter,
        PASSWORD_NEEDS_NUMBER: t.passwordNeedsNumber,
        PASSWORD_NEEDS_SYMBOL: t.passwordNeedsSymbol
      }[passwordError] ?? t.passwordInvalid;
      setError(fieldError);
      return;
    }

    try {
      await apiClient.registerUser({ username, email, password: normalizedPassword });
      const login = await apiClient.login({ username, password: normalizedPassword });
      localStorage.setItem("token", login.token);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : t.failed);
    } finally {
      setPending(false);
    }
  };

  return (
    <main className="mx-auto max-w-lg">
      <section className="glass-card p-xl">
        <div className="mb-lg flex items-center gap-sm">
          <UserPlusIcon className="h-7 w-7 text-cta" aria-hidden="true" />
          <h1 className="text-2xl font-black">{t.title}</h1>
        </div>
        <form onSubmit={onSubmit} className="space-y-md" aria-label="register form">
          <div>
            <label htmlFor="username">{t.username}</label>
            <input id="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
          </div>
          <div>
            <label htmlFor="email">{t.email}</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div>
            <label htmlFor="password">{t.password}</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              required
            />
            <p className="mt-xs text-xs text-white/70">{t.passwordHint}</p>
          </div>
          {error ? <p className="text-sm text-red-200">{error}</p> : null}
          <button type="submit" className="btn-base btn-cta w-full" disabled={pending}>
            {pending ? t.creating : t.create}
          </button>
        </form>
      </section>
    </main>
  );
}

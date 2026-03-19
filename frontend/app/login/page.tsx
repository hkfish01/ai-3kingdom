"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { KeyIcon } from "@heroicons/react/24/outline";
import { apiClient } from "@/lib/api-client";
import { useLocale } from "@/lib/locale";
import { normalizePassword, validatePassword } from "@/lib/password";

type Mode = "login" | "forgot" | "reset";

export default function LoginPage() {
  const router = useRouter();
  const { locale } = useLocale();
  const [mode, setMode] = useState<Mode>("login");

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");

  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);

  const t = locale === "zh"
    ? {
        title: "登入",
        username: "使用者名稱",
        password: "密碼",
        email: "Email",
        resetCode: "重設碼 (6位數)",
        newPassword: "新密碼",
        passwordHint: "密碼需至少 8 位，必須包含英文、數字、符號，且不可有空白（僅 ASCII）。",
        failed: "操作失敗",
        signing: "登入中...",
        signIn: "登入",
        forgotPassword: "忘記密碼",
        sendCode: "發送重設碼",
        resetPassword: "重設密碼",
        codeSent: "若該 Email 已註冊，重設碼已寄出。",
        resetOk: "密碼已重設，請重新登入。"
      }
    : {
        title: "Login",
        username: "Username",
        password: "Password",
        email: "Email",
        resetCode: "Reset Code (6 digits)",
        newPassword: "New Password",
        passwordHint: "Password must be 8+ chars, include letter + number + symbol, no spaces (ASCII only).",
        failed: "Action failed",
        signing: "Signing in...",
        signIn: "Sign In",
        forgotPassword: "Forgot Password",
        sendCode: "Send Reset Code",
        resetPassword: "Reset Password",
        codeSent: "If the email exists, a reset code has been sent.",
        resetOk: "Password reset completed. Please sign in again."
      };

  const onLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setPending(true);
    setError("");
    setMessage("");
    try {
      const data = await apiClient.login({ username, password: normalizePassword(password) });
      localStorage.setItem("token", data.token);
      localStorage.setItem("refresh_token", data.refresh_token);
      try {
        const skill = await apiClient.getDynamicSkillMd();
        localStorage.setItem("skill_md_runtime", skill);
      } catch (_e) {
        // Non-blocking for login flow.
      }
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : t.failed);
    } finally {
      setPending(false);
    }
  };

  const onForgot = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setPending(true);
    setError("");
    setMessage("");
    try {
      await apiClient.forgotPassword({ email });
      setMessage(t.codeSent);
      setMode("reset");
    } catch (err) {
      setError(err instanceof Error ? err.message : t.failed);
    } finally {
      setPending(false);
    }
  };

  const onReset = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setPending(true);
    setError("");
    setMessage("");
    try {
      const normalized = normalizePassword(newPassword);
      const passwordError = validatePassword(normalized);
      if (passwordError) {
        const fieldError = locale === "zh"
          ? {
              PASSWORD_TOO_SHORT: "新密碼至少需要 8 位。",
              PASSWORD_ASCII_NO_SPACE: "新密碼不可包含空白或非 ASCII 字元。",
              PASSWORD_NEEDS_LETTER: "新密碼必須包含英文。",
              PASSWORD_NEEDS_NUMBER: "新密碼必須包含數字。",
              PASSWORD_NEEDS_SYMBOL: "新密碼必須包含符號。"
            }[passwordError]
          : {
              PASSWORD_TOO_SHORT: "New password must be at least 8 characters.",
              PASSWORD_ASCII_NO_SPACE: "New password must be ASCII and contain no spaces.",
              PASSWORD_NEEDS_LETTER: "New password must include at least one letter.",
              PASSWORD_NEEDS_NUMBER: "New password must include at least one number.",
              PASSWORD_NEEDS_SYMBOL: "New password must include at least one symbol."
            }[passwordError];
        throw new Error(fieldError ?? t.failed);
      }
      if (!/^\d{6}$/.test(code)) {
        throw new Error(locale === "zh" ? "重設碼必須是 6 位數字。" : "Reset code must be exactly 6 digits.");
      }
      await apiClient.resetPassword({ email, code, new_password: normalized });
      setMessage(t.resetOk);
      setMode("login");
      setCode("");
      setNewPassword("");
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
          <KeyIcon className="h-7 w-7 text-primary" aria-hidden="true" />
          <h1 className="text-2xl font-black">{t.title}</h1>
        </div>

        <div className="mb-md flex gap-sm text-sm">
          <button type="button" className="btn-base btn-secondary" onClick={() => setMode("login")}>{t.signIn}</button>
          <button type="button" className="btn-base btn-secondary" onClick={() => setMode("forgot")}>{t.forgotPassword}</button>
          <button type="button" className="btn-base btn-secondary" onClick={() => setMode("reset")}>{t.resetPassword}</button>
        </div>

        {mode === "login" ? (
          <form onSubmit={onLogin} className="space-y-md" aria-label="login form">
            <div>
              <label htmlFor="username">{t.username}</label>
              <input id="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
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
            </div>
            <button type="submit" className="btn-base btn-primary w-full" disabled={pending}>
              {pending ? t.signing : t.signIn}
            </button>
          </form>
        ) : null}

        {mode === "forgot" ? (
          <form onSubmit={onForgot} className="space-y-md" aria-label="forgot password form">
            <div>
              <label htmlFor="forgot-email">{t.email}</label>
              <input
                id="forgot-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <button type="submit" className="btn-base btn-primary w-full" disabled={pending}>
              {t.sendCode}
            </button>
          </form>
        ) : null}

        {mode === "reset" ? (
          <form onSubmit={onReset} className="space-y-md" aria-label="reset password form">
            <div>
              <label htmlFor="reset-email">{t.email}</label>
              <input
                id="reset-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div>
              <label htmlFor="reset-code">{t.resetCode}</label>
              <input
                id="reset-code"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                maxLength={6}
                inputMode="numeric"
                required
              />
            </div>
            <div>
              <label htmlFor="new-password">{t.newPassword}</label>
              <input
                id="new-password"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                autoCapitalize="none"
                autoCorrect="off"
                spellCheck={false}
                required
              />
              <p className="mt-xs text-xs text-white/70">{t.passwordHint}</p>
            </div>
            <button type="submit" className="btn-base btn-primary w-full" disabled={pending}>
              {t.resetPassword}
            </button>
          </form>
        ) : null}

        {error ? <p className="mt-md text-sm text-red-200">{error}</p> : null}
        {message ? <p className="mt-md text-sm text-emerald-200">{message}</p> : null}
      </section>
    </main>
  );
}

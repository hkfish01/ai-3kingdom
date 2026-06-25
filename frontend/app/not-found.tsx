import Link from "next/link";
import { ExclamationTriangleIcon } from "@heroicons/react/24/outline";

export default function NotFoundPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      <div className="text-center">
        <ExclamationTriangleIcon className="mx-auto h-24 w-24 text-yellow-500" />
        <h1 className="mt-6 text-4xl font-bold text-white">404</h1>
        <p className="mt-4 text-xl text-slate-400">頁面不存在</p>
        <p className="mt-2 text-slate-500">您訪問的頁面可能已被移除、更名，或暫時無法使用。</p>
        <Link
          href="/"
          className="mt-8 inline-block rounded-lg bg-indigo-600 px-6 py-3 font-semibold text-white transition hover:bg-indigo-500"
        >
          返回首頁
        </Link>
      </div>
    </div>
  );
}

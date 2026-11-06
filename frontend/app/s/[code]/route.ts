import { NextRequest, NextResponse } from "next/server";

/**
 * 對外分享用的短網址：/s/{code} → /world/public/s/{code} → 站內目標。
 *
 * 刻意只做一層同源 302，讓後端負責驗證短碼、記點擊與最終重導：
 * - 不必改 nginx（既有的 location /world/ 已轉給 FastAPI）；
 * - frontend 不需要知道 container 內部 API 位址，也不用新增環境變數；
 * - 無效短碼仍會到後端領 404，不會被拿去猜路徑。
 *
 * Location 固定用相對路徑：在 reverse proxy 後，從請求網址推導出來的 origin
 * 會是 container 內部的 0.0.0.0:3000，對外分享連結會直接 502。相對 Location
 * 由瀏覽器用目前 origin 解析，且不含任何外部輸入，沒有 open redirect 風險。
 */
export const dynamic = "force-dynamic";

const CODE_PATTERN = /^[0-9a-f]{8}$/;

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ code: string }> }
) {
  const { code } = await params;
  const safe = CODE_PATTERN.test(code ?? "") ? code : "invalid";
  return new NextResponse(null, {
    status: 302,
    headers: {
      Location: `/world/public/s/${safe}`,
      "Cache-Control": "no-store"
    }
  });
}

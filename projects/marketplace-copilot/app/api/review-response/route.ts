import { NextRequest, NextResponse } from "next/server";
import { createLLMProvider } from "@/lib/llm";
import { generateReviewResponse } from "@/lib/generation";
import { errorResponse, requireFields } from "@/lib/http";

export const runtime = "nodejs";

/**
 * POST /api/review-response
 * По тексту негативного отзыва возвращает черновик вежливого ответа продавца.
 */
export async function POST(req: NextRequest) {
  try {
    const body = (await req.json()) as { review: string; productName?: string };

    const missing = requireFields(body, ["review"]);
    if (missing) {
      return NextResponse.json({ error: missing }, { status: 400 });
    }

    const llm = createLLMProvider();
    const response = await generateReviewResponse(
      llm,
      body.review.trim(),
      body.productName?.trim() || undefined,
    );

    return NextResponse.json({ provider: llm.name, response });
  } catch (e) {
    return errorResponse(e);
  }
}

import { NextRequest, NextResponse } from "next/server";
import { createLLMProvider } from "@/lib/llm";
import { generateSeoKeywords, ProductInput } from "@/lib/generation";
import { errorResponse, requireFields } from "@/lib/http";

export const runtime = "nodejs";

/**
 * POST /api/seo
 * Отдельным запросом к LLM собирает SEO-ключевые слова для карточки.
 */
export async function POST(req: NextRequest) {
  try {
    const body = (await req.json()) as ProductInput;

    const missing = requireFields(body, ["name", "category", "features"]);
    if (missing) {
      return NextResponse.json({ error: missing }, { status: 400 });
    }

    const input: ProductInput = {
      name: body.name.trim(),
      category: body.category.trim(),
      features: body.features.trim(),
    };

    const llm = createLLMProvider();
    const keywords = await generateSeoKeywords(llm, input);

    return NextResponse.json({ provider: llm.name, keywords });
  } catch (e) {
    return errorResponse(e);
  }
}

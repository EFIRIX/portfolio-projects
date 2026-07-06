import { NextRequest, NextResponse } from "next/server";
import { createLLMProvider } from "@/lib/llm";
import { generateCard, ProductInput } from "@/lib/generation";
import { PLATFORM_IDS, PlatformId } from "@/config/platforms.config";
import { errorResponse, requireFields } from "@/lib/http";

export const runtime = "nodejs";

/**
 * POST /api/generate
 * Генерирует карточки для указанных площадок (по умолчанию — обе).
 * Раздельная генерация WB/Ozon: каждая площадка получает свой набор лимитов.
 */
export async function POST(req: NextRequest) {
  try {
    const body = (await req.json()) as ProductInput & {
      platforms?: PlatformId[];
    };

    const missing = requireFields(body, ["name", "category", "features"]);
    if (missing) {
      return NextResponse.json({ error: missing }, { status: 400 });
    }

    const platforms =
      body.platforms && body.platforms.length > 0
        ? body.platforms.filter((p) => PLATFORM_IDS.includes(p))
        : PLATFORM_IDS;

    const input: ProductInput = {
      name: body.name.trim(),
      category: body.category.trim(),
      features: body.features.trim(),
    };

    const llm = createLLMProvider();
    // Разные площадки независимы — считаем параллельно.
    const cards = await Promise.all(
      platforms.map((p) => generateCard(llm, p, input)),
    );

    return NextResponse.json({ provider: llm.name, cards });
  } catch (e) {
    return errorResponse(e);
  }
}

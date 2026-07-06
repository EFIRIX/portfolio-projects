import { NextResponse } from "next/server";
import { LLMError } from "@/lib/llm";

/** Единая обёртка ошибок для API-роутов. */
export function errorResponse(e: unknown): NextResponse {
  if (e instanceof LLMError) {
    // 502 — проблема на стороне внешнего LLM/конфигурации ключей.
    return NextResponse.json(
      { error: e.message, provider: e.provider },
      { status: 502 },
    );
  }
  const message = e instanceof Error ? e.message : "Внутренняя ошибка";
  return NextResponse.json({ error: message }, { status: 500 });
}

/** Проверка обязательных непустых строковых полей. */
export function requireFields<T extends object>(
  body: T,
  fields: (keyof T)[],
): string | null {
  for (const f of fields) {
    const v = (body as Record<keyof T, unknown>)[f];
    if (typeof v !== "string" || v.trim() === "") {
      return `Поле "${String(f)}" обязательно`;
    }
  }
  return null;
}

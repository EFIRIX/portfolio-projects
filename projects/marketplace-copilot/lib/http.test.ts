import { describe, it, expect } from "vitest";
import { requireFields } from "@/lib/http";

/**
 * Тесты валидации ввода — чистая логика, не зависящая от Next runtime.
 *
 * Покрывают пункт чек-листа "невалидный ввод": requireFields используется
 * всеми тремя роутами (/api/generate, /api/seo, /api/review-response),
 * чтобы отлупить пустое тело запроса человекочитаемой ошибкой 400.
 *
 * errorResponse (обёртка LLMError → 502 / Error → 500) намеренно не
 * тестируется здесь: она зависит от NextResponse из next/server, что
 * тянет Next-runtime в vitest. Её поведение тривиально видно из кода, а
 * проброс ошибки провайдера покрыт в generation.test.ts (ThrowingProvider),
 * где роут затем превратит её в 502 через errorResponse.
 */

describe("requireFields — валидация ввода", () => {
  it("возвращает null, если все обязательные поля непустые", () => {
    const missing = requireFields(
      { name: "Наушники", category: "Электроника", features: "BT 5.3" },
      ["name", "category", "features"],
    );
    expect(missing).toBeNull();
  });

  it("возвращает сообщение для пустой строки", () => {
    const missing = requireFields(
      { name: "", category: "Электроника", features: "BT 5.3" },
      ["name", "category", "features"],
    );
    expect(missing).toBe('Поле "name" обязательно');
  });

  it("возвращает сообщение для строки из пробелов", () => {
    const missing = requireFields(
      { name: "Наушники", category: "   ", features: "BT 5.3" },
      ["name", "category", "features"],
    );
    expect(missing).toBe('Поле "category" обязательно');
  });

  it("возвращает сообщение для отсутствующего поля", () => {
    const missing = requireFields(
      { name: "Наушники", category: "Электроника" },
      ["name", "category", "features"],
    );
    expect(missing).toBe('Поле "features" обязательно');
  });

  it("не строковое значение считается невалидным", () => {
    const missing = requireFields(
      { name: 123, category: "Электроника", features: "BT 5.3" },
      ["name", "category", "features"],
    );
    expect(missing).toBe('Поле "name" обязательно');
  });

  it("пустой отзыв отклоняется — сценарий для /api/review-response", () => {
    const missing = requireFields({ review: "" }, ["review"]);
    expect(missing).toBe('Поле "review" обязательно');
  });
});

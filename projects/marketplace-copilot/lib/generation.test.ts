import { describe, it, expect } from "vitest";
import {
  countChars,
  generateCard,
  generateSeoKeywords,
  generateReviewResponse,
  ProductInput,
} from "@/lib/generation";
import { PLATFORMS } from "@/config/platforms.config";
import { ChatMessage, LLMProvider } from "@/lib/llm";

/**
 * Тесты доменной логики генерации.
 *
 * Покрывают ключевое требование ТЗ: лимиты проверяются кодом после генерации,
 * а при превышении делается повторный запрос (не механическая обрезка).
 * Все тесты идут против mock-провайдера, реальные LLM не дёргаются.
 *
 * Внимание: generateCard запускает title и description параллельно через
 * Promise.all, поэтому mock-провайдер НЕ может опираться на порядок вызовов.
 * Вместо этого он маршрутизирует ответ по содержимому user-сообщения:
 * и генерация, и shrink-запрос содержат label поля («Наименование»,
 * «Описание» …) — по нему и различаем. Число вызовов для каждого поля
 * считается отдельно, давая индекс в массиве ответов (попытки shrink).
 */

const SAMPLE = "а"; // один кириллический символ = один code point
function repeat(s: string, n: number): string {
  return s.repeat(n);
}

/**
 * Провайдер, который отвечает по содержимому запроса.
 *  - titleReplies / descReplies: ответы по попыткам (1-я генерация, затем shrink).
 *    Если массив короче, чем число вызовов — берётся последний элемент
 *    (полезно для «всегда длинный»).
 */
class FieldAwareProvider implements LLMProvider {
  readonly name = "mock";
  private titleCalls = 0;
  private descCalls = 0;
  constructor(
    private readonly titleReplies: string[],
    private readonly descReplies: string[],
  ) {}
  async complete(messages: ChatMessage[]): Promise<string> {
    const userText = messages.map((m) => m.content).join("\n");
    // И генерация, и shrink-запрос содержат label поля («Наименование»,
    // «Описание» …), поэтому определяем поле по нему. Число вызовов
    // для каждого поля растёт отдельно — это и есть индекс в массиве
    // ответов (1-я генерация → [0], shrink → [1], и т.д.).
    const isTitle =
      userText.includes("Наименование") || userText.includes("Название товара");
    const isDesc =
      userText.includes("Описание") || userText.includes("Аннотация");

    if (isTitle) {
      const i = Math.min(this.titleCalls, this.titleReplies.length - 1);
      this.titleCalls += 1;
      return this.titleReplies[i];
    }
    // isDesc (или любой прочий вызов — на практике всегда description).
    const i = Math.min(this.descCalls, this.descReplies.length - 1);
    this.descCalls += 1;
    return this.descReplies[i];
  }
}

/** Провайдер, который кидается указанной ошибкой на каждый вызов. */
class ThrowingProvider implements LLMProvider {
  readonly name = "mock-throw";
  constructor(private readonly err: Error) {}
  async complete(): Promise<string> {
    throw this.err;
  }
}

/** Провайдер с одним фиксированным ответом на любой вызов. */
class FixedProvider implements LLMProvider {
  readonly name = "mock-fixed";
  constructor(private readonly reply: string) {}
  async complete(): Promise<string> {
    return this.reply;
  }
}

const INPUT: ProductInput = {
  name: "Беспроводные наушники TWS Pro",
  category: "Электроника / Наушники",
  features: "Bluetooth 5.3, шумоподавление, 30 часов работы",
};

describe("countChars", () => {
  it("считает кириллицу по символам, не по байтам", () => {
    expect(countChars("Наушники TWS Pro")).toBe(16);
  });

  it("trim'ит пробелы по краям перед подсчётом", () => {
    expect(countChars("  abc  ")).toBe(3);
  });

  it("эмодзи и суррогатные пары — один символ, не два", () => {
    // 🎧 = U+1F3A7 (суррогатная пара в UTF-16, но один code point).
    expect(countChars("🎧")).toBe(1);
    expect(countChars("🎧🎧abc")).toBe(5);
  });
});

describe("generateCard — валидация длины", () => {
  it("укладывается с первого раза: attempts=1, withinLimit=true", async () => {
    const title = repeat(SAMPLE, PLATFORMS.wildberries.title.maxChars);
    const desc = repeat(SAMPLE, 100);
    const llm = new FieldAwareProvider([title], [desc]);

    const card = await generateCard(llm, "wildberries", INPUT);

    expect(card.title.attempts).toBe(1);
    expect(card.title.withinLimit).toBe(true);
    expect(card.title.charCount).toBe(PLATFORMS.wildberries.title.maxChars);
    expect(card.description.attempts).toBe(1);
    expect(card.description.withinLimit).toBe(true);
  });

  it("превышение → повторный запрос сократить → уложились (attempts=2)", async () => {
    // Описание: 1-я попытка длиннее лимита WB (5000), 2-я — в пределах.
    const tooLong = repeat(
      SAMPLE,
      PLATFORMS.wildberries.description.maxChars + 200,
    );
    const fits = repeat(SAMPLE, 200);
    const titleFits = repeat(SAMPLE, 30);
    const llm = new FieldAwareProvider([titleFits], [tooLong, fits]);

    const card = await generateCard(llm, "wildberries", INPUT);

    expect(card.description.attempts).toBe(2);
    expect(card.description.withinLimit).toBe(true);
    expect(card.description.charCount).toBe(200);
    // Текст — именно второй (сокращённый) вариант, а не обрезка первого.
    expect(card.description.text).toBe(fits);
  });

  it("модель не укладывается за все попытки → фолбэк-обрезка, withinLimit=false", async () => {
    // Название Ozon: всегда длиннее лимита (200), даже после 3 попыток сократить.
    const alwaysLong = repeat(SAMPLE, PLATFORMS.ozon.title.maxChars + 50);
    const descFits = repeat(SAMPLE, 100);
    const llm = new FieldAwareProvider([alwaysLong], [descFits]);

    const card = await generateCard(llm, "ozon", INPUT);

    expect(card.title.withinLimit).toBe(false);
    expect(card.title.attempts).toBe(4); // 1 генерация + 3 shrink
    expect(card.title.charCount).toBe(PLATFORMS.ozon.title.maxChars);
    expect([...card.title.text].length).toBe(PLATFORMS.ozon.title.maxChars);
    expect(card.description.withinLimit).toBe(true);
  });
});

describe("generateCard — разные лимиты WB vs Ozon (ключевое требование ТЗ)", () => {
  it("WB и Ozon имеют разные maxChars для title и description", () => {
    expect(PLATFORMS.wildberries.title.maxChars).not.toBe(
      PLATFORMS.ozon.title.maxChars,
    );
    expect(PLATFORMS.wildberries.description.maxChars).not.toBe(
      PLATFORMS.ozon.description.maxChars,
    );
  });

  it("карточки под WB и Ozon возвращают лимиты из своего конфига", async () => {
    const wb = new FieldAwareProvider(
      [repeat(SAMPLE, 30)],
      [repeat(SAMPLE, 100)],
    );
    const oz = new FieldAwareProvider(
      [repeat(SAMPLE, 30)],
      [repeat(SAMPLE, 100)],
    );

    const [wbCard, ozCard] = await Promise.all([
      generateCard(wb, "wildberries", INPUT),
      generateCard(oz, "ozon", INPUT),
    ]);

    expect(wbCard.title.maxChars).toBe(PLATFORMS.wildberries.title.maxChars);
    expect(ozCard.title.maxChars).toBe(PLATFORMS.ozon.title.maxChars);
    expect(wbCard.description.maxChars).toBe(
      PLATFORMS.wildberries.description.maxChars,
    );
    expect(ozCard.description.maxChars).toBe(
      PLATFORMS.ozon.description.maxChars,
    );
    expect(wbCard.platformName).toBe("Wildberries");
    expect(ozCard.platformName).toBe("Ozon");
  });
});

describe("generateSeoKeywords — парсинг и ограничение", () => {
  it("разделяет по запятым и чистит нумерацию", async () => {
    const raw = "1. наушники tws, 2) беспроводные наушники; шумоподавление";
    const llm = new FixedProvider(raw);
    const kw = await generateSeoKeywords(llm, INPUT);
    expect(kw).toEqual([
      "наушники tws",
      "беспроводные наушники",
      "шумоподавление",
    ]);
  });

  it("не отдаёт больше SEO_KEYWORDS.max", async () => {
    const many = Array.from({ length: 30 }, (_, i) => `ключ${i}`).join(", ");
    const llm = new FixedProvider(many);
    const kw = await generateSeoKeywords(llm, INPUT);
    // max = 15 из конфига.
    expect(kw.length).toBeLessThanOrEqual(15);
    expect(kw.length).toBe(15);
  });

  it("пустой ответ LLM → пустой массив, не падение", async () => {
    const llm = new FixedProvider("   ");
    const kw = await generateSeoKeywords(llm, INPUT);
    expect(kw).toEqual([]);
  });
});

describe("generateReviewResponse — ответ на отзыв", () => {
  it("возвращает текст ответа от провайдера", async () => {
    const reply = "Здравствуйте! Спасибо за обратную связь.";
    const llm = new FixedProvider(reply);
    const out = await generateReviewResponse(llm, "Пришёл бракованный товар");
    expect(out).toBe(reply);
  });

  it("пробрасывает ошибку провайдера (недоступный API)", async () => {
    const llm = new ThrowingProvider(new Error("upstream down"));
    await expect(
      generateReviewResponse(llm, "Плохой товар"),
    ).rejects.toThrow("upstream down");
  });
});

describe("обработка ошибок провайдера (недоступный API)", () => {
  it("generateCard пробрасывает ошибку LLM наружу — роут превратит её в 502", async () => {
    const llm = new ThrowingProvider(new Error("GigaChat вернул 500"));
    await expect(generateCard(llm, "wildberries", INPUT)).rejects.toThrow(
      "GigaChat вернул 500",
    );
  });
});

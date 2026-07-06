import {
  FieldLimit,
  PlatformConfig,
  PLATFORMS,
  PlatformId,
  SEO_KEYWORDS,
} from "@/config/platforms.config";
import { ChatMessage, LLMProvider } from "@/lib/llm";

export interface ProductInput {
  /** Название товара (как продавец его называет). */
  name: string;
  /** Категория товара. */
  category: string;
  /** Ключевые характеристики / особенности (свободный текст). */
  features: string;
}

export interface GeneratedField {
  label: string;
  text: string;
  charCount: number;
  maxChars: number;
  /** Уложились ли в лимит после всех попыток. */
  withinLimit: boolean;
  /** Сколько запросов к LLM ушло на это поле (1 = с первого раза). */
  attempts: number;
}

export interface PlatformCard {
  platformId: PlatformId;
  platformName: string;
  title: GeneratedField;
  description: GeneratedField;
}

/** Сколько раз повторно просить сократить, прежде чем сдаться. */
const MAX_SHRINK_ATTEMPTS = 3;

/**
 * Подсчёт длины ровно так, как её считают площадки — по символам (code points),
 * а не по UTF-16 code units. Эмодзи и подобное считаются как один символ.
 */
export function countChars(text: string): number {
  return [...text.trim()].length;
}

/** Механически укоротить строку до N символов по границе code point. */
function hardTrim(text: string, maxChars: number): string {
  const chars = [...text.trim()];
  if (chars.length <= maxChars) return text.trim();
  return chars.slice(0, maxChars).join("").trim();
}

function systemPrompt(platform: PlatformConfig): ChatMessage {
  return {
    role: "system",
    content:
      `Ты — опытный копирайтер маркетплейса ${platform.name}. ` +
      `${platform.styleNotes} ` +
      "Пиши на русском, без markdown-разметки, без кавычек вокруг ответа. " +
      "Возвращай ТОЛЬКО текст запрошенного поля, без пояснений и заголовков.",
  };
}

function fieldPrompt(
  input: ProductInput,
  field: FieldLimit,
): string {
  return (
    `Товар: ${input.name}\n` +
    `Категория: ${input.category}\n` +
    `Ключевые характеристики: ${input.features}\n\n` +
    `Составь поле «${field.label}». ${field.guidance}\n` +
    `ВАЖНО: уложись примерно в ${field.targetChars} символов и ни в коем случае ` +
    `не превышай ${field.maxChars} символов.`
  );
}

/**
 * Сгенерировать одно поле и programmatically проверить длину.
 *
 * Ключевая идея ТЗ: если LLM превысила лимит, мы НЕ режем текст механически
 * (это ломает смысл), а делаем повторный запрос с явным указанием сократить,
 * передавая модели её собственный слишком длинный вариант и фактический перелёт.
 * Механическая обрезка используется лишь как крайний фолбэк, когда модель
 * так и не уложилась за MAX_SHRINK_ATTEMPTS попыток — и это честно помечается.
 */
async function generateField(
  llm: LLMProvider,
  platform: PlatformConfig,
  input: ProductInput,
  field: FieldLimit,
): Promise<GeneratedField> {
  const sys = systemPrompt(platform);
  const messages: ChatMessage[] = [sys, { role: "user", content: fieldPrompt(input, field) }];

  let text = await llm.complete(messages, { temperature: 0.4 });
  let attempts = 1;

  while (countChars(text) > field.maxChars && attempts <= MAX_SHRINK_ATTEMPTS) {
    const current = countChars(text);
    const over = current - field.maxChars;
    // Отдаём модели её же вариант и просим осмысленно сжать, сохранив суть.
    const shrink: ChatMessage[] = [
      sys,
      {
        role: "user",
        content:
          `Вот текст поля «${field.label}» (${current} символов), он превышает ` +
          `лимит ${platform.name} на ${over} символов:\n\n${text}\n\n` +
          `Сократи его до ${field.targetChars} символов, СОХРАНИВ смысл и ключевые ` +
          `выгоды. Убери воду и повторы, не обрывай на полуслове. ` +
          `Верни только сокращённый текст.`,
      },
    ];
    text = await llm.complete(shrink, { temperature: 0.2 });
    attempts += 1;
  }

  let withinLimit = countChars(text) <= field.maxChars;
  if (!withinLimit) {
    // Крайний фолбэк: модель не справилась. Режем, но честно сообщаем флагом.
    text = hardTrim(text, field.maxChars);
    withinLimit = false;
  }

  return {
    label: field.label,
    text,
    charCount: countChars(text),
    maxChars: field.maxChars,
    withinLimit,
    attempts,
  };
}

/** Сгенерировать полную карточку под конкретную площадку. */
export async function generateCard(
  llm: LLMProvider,
  platformId: PlatformId,
  input: ProductInput,
): Promise<PlatformCard> {
  const platform = PLATFORMS[platformId];
  // Заголовок и описание независимы — генерируем параллельно.
  const [title, description] = await Promise.all([
    generateField(llm, platform, input, platform.title),
    generateField(llm, platform, input, platform.description),
  ]);

  return {
    platformId,
    platformName: platform.name,
    title,
    description,
  };
}

/** SEO-ключевые слова отдельным запросом. Количество — правило из конфига. */
export async function generateSeoKeywords(
  llm: LLMProvider,
  input: ProductInput,
): Promise<string[]> {
  const messages: ChatMessage[] = [
    {
      role: "system",
      content:
        "Ты — SEO-специалист маркетплейсов. Возвращай только ключевые слова " +
        "через запятую, без нумерации, без пояснений.",
    },
    {
      role: "user",
      content:
        `Товар: ${input.name}\nКатегория: ${input.category}\n` +
        `Характеристики: ${input.features}\n\n` +
        `Дай ${SEO_KEYWORDS.min}–${SEO_KEYWORDS.max} поисковых ключевых фраз, ` +
        `по которым такой товар ищут на Wildberries и Ozon. ` +
        `Включи синонимы и сопутствующие запросы. Через запятую.`,
    },
  ];

  const raw = await llm.complete(messages, { temperature: 0.5 });
  const keywords = raw
    .split(/[,\n;]+/)
    .map((k) => k.replace(/^\s*\d+[.)]\s*/, "").trim())
    .filter(Boolean);

  // Программно приводим к диапазону из конфига.
  return keywords.slice(0, SEO_KEYWORDS.max);
}

/** Черновик вежливого, конкретного ответа на негативный отзыв. */
export async function generateReviewResponse(
  llm: LLMProvider,
  review: string,
  productName?: string,
): Promise<string> {
  const messages: ChatMessage[] = [
    {
      role: "system",
      content:
        "Ты — менеджер по работе с отзывами на маркетплейсе. Пиши вежливо, " +
        "по-человечески, без шаблонных отписок. Признай проблему, дай конкретику, " +
        "предложи решение. Без markdown, 3–5 предложений.",
    },
    {
      role: "user",
      content:
        (productName ? `Товар: ${productName}\n` : "") +
        `Негативный отзыв покупателя:\n"${review}"\n\n` +
        "Напиши черновик ответа продавца: поблагодари за обратную связь, " +
        "ответь по сути претензии, предложи конкретный следующий шаг.",
    },
  ];

  return llm.complete(messages, { temperature: 0.5 });
}

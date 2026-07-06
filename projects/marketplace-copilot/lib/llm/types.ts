/**
 * Абстракция над LLM-провайдером.
 *
 * Вся бизнес-логика (генерация карточек, валидация лимитов) работает ТОЛЬКО
 * с этим интерфейсом и ничего не знает про GigaChat/YandexGPT. Чтобы добавить
 * нового провайдера, достаточно реализовать LLMProvider и зарегистрировать его
 * в фабрике (lib/llm/index.ts).
 */

export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface CompletionOptions {
  /** 0..1 — креативность. Для коммерческих текстов держим невысокой. */
  temperature?: number;
  /** Верхняя граница длины ответа в токенах. */
  maxTokens?: number;
}

export interface LLMProvider {
  /** Имя провайдера для логов и README. */
  readonly name: string;
  /**
   * Единственная операция, которая нужна доменному коду:
   * получить текстовый ответ на список сообщений.
   */
  complete(messages: ChatMessage[], options?: CompletionOptions): Promise<string>;
}

/** Единый тип ошибки провайдера, чтобы API-роуты не зависели от деталей. */
export class LLMError extends Error {
  constructor(
    message: string,
    public readonly provider: string,
    public readonly cause?: unknown,
  ) {
    super(message);
    this.name = "LLMError";
  }
}

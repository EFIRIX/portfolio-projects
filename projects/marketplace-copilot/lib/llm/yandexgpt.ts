import { ChatMessage, CompletionOptions, LLMError, LLMProvider } from "./types";

const COMPLETION_URL =
  "https://llm.api.cloud.yandex.net/foundationModels/v1/completion";

/**
 * YandexGPT — альтернативный провайдер, подключается через тот же LLMProvider.
 *
 * Существует, чтобы доказать, что абстракция настоящая: доменный код не меняется
 * при смене провайдера, различается только эта реализация и переменные окружения.
 */
export class YandexGPTProvider implements LLMProvider {
  readonly name = "yandexgpt";

  constructor(
    private readonly apiKey: string,
    private readonly folderId: string,
    private readonly model: string,
  ) {
    if (!apiKey || !folderId) {
      throw new LLMError(
        "YANDEX_API_KEY и YANDEX_FOLDER_ID должны быть заданы",
        "yandexgpt",
      );
    }
  }

  async complete(
    messages: ChatMessage[],
    options: CompletionOptions = {},
  ): Promise<string> {
    const modelUri = `gpt://${this.folderId}/${this.model}/latest`;

    let res: Response;
    try {
      res = await fetch(COMPLETION_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Api-Key ${this.apiKey}`,
        },
        body: JSON.stringify({
          modelUri,
          completionOptions: {
            stream: false,
            temperature: options.temperature ?? 0.3,
            maxTokens: String(options.maxTokens ?? 1500),
          },
          // YandexGPT использует роль "system" | "user" | "assistant" -> text.
          messages: messages.map((m) => ({ role: m.role, text: m.content })),
        }),
      });
    } catch (e) {
      throw new LLMError("Сетевая ошибка запроса к YandexGPT", "yandexgpt", e);
    }

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new LLMError(
        `YandexGPT вернул ${res.status}: ${text}`,
        "yandexgpt",
      );
    }

    const data = (await res.json()) as {
      result?: { alternatives?: { message?: { text?: string } }[] };
    };
    const content = data.result?.alternatives?.[0]?.message?.text;
    if (!content) {
      throw new LLMError("YandexGPT вернул пустой ответ", "yandexgpt");
    }
    return content.trim();
  }
}

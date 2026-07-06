import { randomUUID } from "crypto";
import { ChatMessage, CompletionOptions, LLMError, LLMProvider } from "./types";

const OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth";
const CHAT_URL =
  "https://gigachat.devices.sberbank.ru/api/v1/chat/completions";

interface CachedToken {
  accessToken: string;
  /** Unix ms, когда токен истекает. */
  expiresAt: number;
}

/**
 * GigaChat (Сбер) — основной провайдер.
 *
 * Схема авторизации двухступенчатая:
 *  1. По Authorization key (base64 client_id:client_secret) получаем короткоживущий
 *     OAuth access-токен на выбранный scope.
 *  2. Access-токен используем как Bearer для чат-запросов.
 *
 * Токен кэшируется в памяти процесса и переиспользуется до истечения.
 *
 * Прим.: у GigaChat самоподписанный корневой сертификат НУЦ Минцифры. В проде
 * его добавляют в доверенные (NODE_EXTRA_CA_CERTS). Для локальной разработки
 * это описано в README; тут мы не отключаем проверку TLS в коде.
 */
export class GigaChatProvider implements LLMProvider {
  readonly name = "gigachat";
  private token: CachedToken | null = null;

  constructor(
    private readonly authKey: string,
    private readonly scope: string,
    private readonly model: string,
  ) {
    if (!authKey) {
      throw new LLMError(
        "GIGACHAT_AUTH_KEY не задан в окружении",
        "gigachat",
      );
    }
  }

  private async getAccessToken(): Promise<string> {
    const now = Date.now();
    // Обновляем заранее — за 60 сек до истечения.
    if (this.token && this.token.expiresAt - 60_000 > now) {
      return this.token.accessToken;
    }

    const body = new URLSearchParams({ scope: this.scope });
    let res: Response;
    try {
      res = await fetch(OAUTH_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          Accept: "application/json",
          RqUID: randomUUID(),
          Authorization: `Basic ${this.authKey}`,
        },
        body,
      });
    } catch (e) {
      throw new LLMError(
        "Не удалось подключиться к OAuth GigaChat (проверьте сеть и TLS-сертификат НУЦ Минцифры)",
        "gigachat",
        e,
      );
    }

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new LLMError(
        `OAuth GigaChat вернул ${res.status}: ${text}`,
        "gigachat",
      );
    }

    const data = (await res.json()) as {
      access_token: string;
      expires_at: number;
    };
    this.token = {
      accessToken: data.access_token,
      // expires_at приходит в Unix ms.
      expiresAt: data.expires_at,
    };
    return this.token.accessToken;
  }

  async complete(
    messages: ChatMessage[],
    options: CompletionOptions = {},
  ): Promise<string> {
    const accessToken = await this.getAccessToken();

    let res: Response;
    try {
      res = await fetch(CHAT_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          model: this.model,
          messages,
          temperature: options.temperature ?? 0.3,
          max_tokens: options.maxTokens ?? 1500,
        }),
      });
    } catch (e) {
      throw new LLMError("Сетевая ошибка запроса к GigaChat", "gigachat", e);
    }

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new LLMError(
        `GigaChat вернул ${res.status}: ${text}`,
        "gigachat",
      );
    }

    const data = (await res.json()) as {
      choices?: { message?: { content?: string } }[];
    };
    const content = data.choices?.[0]?.message?.content;
    if (!content) {
      throw new LLMError("GigaChat вернул пустой ответ", "gigachat");
    }
    return content.trim();
  }
}

import { GigaChatProvider } from "./gigachat";
import { YandexGPTProvider } from "./yandexgpt";
import { LLMError, LLMProvider } from "./types";

export * from "./types";

/**
 * Фабрика провайдера. Единственное место, где доменный код узнаёт, какой
 * конкретно провайдер используется. Выбор — по переменной окружения LLM_PROVIDER.
 */
export function createLLMProvider(): LLMProvider {
  const provider = (process.env.LLM_PROVIDER ?? "gigachat").toLowerCase();

  switch (provider) {
    case "gigachat":
      return new GigaChatProvider(
        process.env.GIGACHAT_AUTH_KEY ?? "",
        process.env.GIGACHAT_SCOPE ?? "GIGACHAT_API_PERS",
        process.env.GIGACHAT_MODEL ?? "GigaChat",
      );
    case "yandexgpt":
      return new YandexGPTProvider(
        process.env.YANDEX_API_KEY ?? "",
        process.env.YANDEX_FOLDER_ID ?? "",
        process.env.YANDEX_MODEL ?? "yandexgpt",
      );
    default:
      throw new LLMError(
        `Неизвестный LLM_PROVIDER: "${provider}". Допустимо: gigachat | yandexgpt`,
        provider,
      );
  }
}

import OpenAI from 'openai';
import { config } from '../config';

export interface LLMProvider {
  streamCompletion(input: {
    messages: { role: 'system' | 'user' | 'assistant'; content: string }[];
    abortSignal?: AbortSignal;
  }): AsyncGenerator<string>;
}

class OpenAILLMProvider implements LLMProvider {
  private client = new OpenAI({ apiKey: config.openaiApiKey });
  async *streamCompletion(input: { messages: { role: 'system' | 'user' | 'assistant'; content: string }[]; abortSignal?: AbortSignal }) {
    const completion = await this.client.chat.completions.create({
      model: config.openaiModel,
      stream: true,
      messages: input.messages
    }, { signal: input.abortSignal });
    for await (const part of completion) {
      const delta = part.choices[0]?.delta?.content;
      if (delta) yield delta;
    }
  }
}

class MockLLMProvider implements LLMProvider {
  async *streamCompletion(input: { messages: { role: 'system' | 'user' | 'assistant'; content: string }[] }) {
    const last = input.messages[input.messages.length - 1]?.content ?? 'hello';
    const text = `I heard you say: ${last}. Here's a short follow-up question.`;
    yield text;
  }
}

export function buildLLMProvider(): LLMProvider {
  if (config.openaiApiKey) return new OpenAILLMProvider();
  return new MockLLMProvider();
}

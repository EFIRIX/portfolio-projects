export const config = {
  port: Number(process.env.PORT ?? 8787),
  openaiApiKey: process.env.OPENAI_API_KEY,
  openaiModel: process.env.OPENAI_MODEL ?? 'gpt-4o-mini',
  ttsModel: process.env.TTS_MODEL ?? 'gpt-4o-mini-tts',
  ttsVoice: process.env.TTS_VOICE ?? 'alloy',
  deepgramApiKey: process.env.DEEPGRAM_API_KEY,
  redisUrl: process.env.REDIS_URL,
  databaseUrl: process.env.DATABASE_URL,
  enableTraceLogs: process.env.ENABLE_TRACE_LOGS === '1'
};

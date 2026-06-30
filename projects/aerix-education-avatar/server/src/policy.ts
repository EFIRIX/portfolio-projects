const RESTRICTED_TOPICS = ['violence', 'extremism', 'self-harm'];

export function violatesPolicy(text: string): boolean {
  const lower = text.toLowerCase();
  return RESTRICTED_TOPICS.some((k) => lower.includes(k));
}

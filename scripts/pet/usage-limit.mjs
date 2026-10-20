// Only inspect structured errors from the current turn, never conversation text.
import { transcriptRecords } from './transcript.mjs';

function isLimit(error) {
  const code = error.codex_error_info ?? error.code ?? error.error?.code;
  const known = ['usage_limit_exceeded', 'usage_limit_reached', 'rate_limit_exceeded',
    'rate_limit', 'insufficient_quota'];
  if (typeof code === 'string' && known.includes(code.toLowerCase())) return true;
  if (code && typeof code === 'object' && known.some(key => Object.hasOwn(code, key))) return true;
  const message = error.message ?? error.error?.message;
  return typeof message === 'string' && /usage[ _-]+limit|rate[ _-]+limit|insufficient[ _-]+quota/i.test(message);
}

export function codexUsageLimited(lines) {
  for (const entry of transcriptRecords(lines)) {
    const payload = entry.payload;
    if (entry.type === 'event_msg' && payload && typeof payload === 'object') {
      if (payload.type === 'error') return isLimit(payload);
      if (['task_started', 'turn_started', 'user_message', 'agent_message'].includes(payload.type)) return false;
    }
    if (entry.type === 'turn_context') return false;
    if (entry.type === 'response_item' && payload?.type === 'message' &&
        (payload.role === 'user' || (payload.role === 'assistant' && (!payload.phase || payload.phase === 'final_answer')))) return false;
  }
  return false;
}

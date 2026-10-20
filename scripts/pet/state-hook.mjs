// Silent, bounded side effect: never controls Claude's decisions.
import { promises as fs } from 'node:fs';
import { dirname } from 'node:path';
import { codexStatePath } from './codex-path.mjs';
import { transcriptTail, transcriptRecords, recordedModel } from './transcript.mjs';
const finish = () => process.exit(0);
const deadline = setTimeout(finish, 650);
process.on('uncaughtException', finish);
process.on('unhandledRejection', finish);
process.stdin.on('error', finish);
let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => {
  input += chunk;
  if (Buffer.byteLength(input) > 1024 * 1024) finish();
});
process.stdin.on('end', async () => {
  let temporary;
  try {
    const data = JSON.parse(input);
    if (!data || typeof data !== 'object') return;
    const event = data.hook_event_name;
    if (event === 'StopFailure' && !['rate_limit', 'billing_error'].includes(data.error)) return;
    const mapping = { UserPromptSubmit: ['running', '考え中…'], PreToolUse: ['running', '作業中…'], PermissionRequest: ['waiting', '入力待ち'], Notification: ['waiting', '入力待ち'], PostToolUseFailure: ['failed', 'エラー'], Stop: ['review', '完了'] };
    mapping.StopFailure = ['sleeping', '寝ています'];
    if (!Object.hasOwn(mapping, event)) return;
    if (event === 'Notification' && !['permission_prompt', 'idle_prompt', 'elicitation_dialog'].includes(data.notification_type)) return;
    const [state, message] = mapping[event];
    const directModel = recordedModel(data, []);
    const lines = !directModel || (event === 'Stop' && typeof data.last_assistant_message !== 'string')
      ? await transcriptTail(data.transcript_path) : [];
    const model = directModel || recordedModel(data, lines);
    let expression = 'normal';
    if (event === 'Stop') {
      let text = data.last_assistant_message;
      if (typeof text !== 'string' && typeof data.transcript_path === 'string') {
        for (const entry of transcriptRecords(lines)) {
          try {
            if (entry.type !== 'assistant' || !entry.message) continue;
            const content = entry.message.content;
            text = typeof content === 'string' ? content : Array.isArray(content) ? content.filter(c => c.type === 'text').map(c => c.text).join('\n') : '';
            break;
          } catch { /* Skip malformed message content. */ }
        }
      }
      const tail = typeof text === 'string' ? text.trimEnd().split(/\r?\n/).slice(-5).join('\n') : '';
      const marks = [...tail.matchAll(/\[表情:([^\]\r\n]*)\]/g)];
      const value = marks.at(-1)?.[1];
      if (['normal', 'smile', 'angry'].includes(value)) expression = value;
    }
    const path = process.env.CLAUDE_PET_STATE_PATH || codexStatePath({ env: { ...process.env, CODEX_PET_STATE_PATH: process.env.CLAUDE_PET_STATE_PATH } }).replace(/codex-state\.json$/, 'state.json');
    await fs.mkdir(dirname(path), { recursive: true });
    temporary = `${path}.${process.pid}.${Date.now()}.tmp`;
    await fs.writeFile(temporary, JSON.stringify({ state, expression, message, model, session_id: typeof data.session_id === 'string' ? data.session_id : '', updated_at: new Date().toISOString() }), { encoding: 'utf8', flag: 'wx' });
    await fs.rename(temporary, path);
  } catch { /* State IO failure must not affect Claude. */ }
  finally {
    if (temporary) await fs.unlink(temporary).catch(() => {});
    clearTimeout(deadline);
    finish();
  }
});

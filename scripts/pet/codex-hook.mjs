// Silent Codex adapter. Never makes approval or continuation decisions.
import { codexStatePath } from './codex-path.mjs';
import { promises as fs } from 'node:fs';
import { dirname } from 'node:path';
import { codexUsageLimited } from './usage-limit.mjs';
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
    let event = data.hook_event_name;
    if (event === 'PostToolUse') {
      const response = data.tool_response;
      const failed = response && typeof response === 'object' && (response.isError === true ||
        (Number.isInteger(response.exit_code) && response.exit_code !== 0));
      const bashFailure = data.tool_name === 'Bash' && typeof response === 'string' &&
        /^Process exited with code [1-9][0-9]*\s*$/m.test(response);
      if (!failed && !bashFailure) return;
      event = 'PostToolUseFailure';
    } else if (!['UserPromptSubmit', 'PreToolUse', 'PermissionRequest', 'Stop'].includes(event)) return;
    const mapping = { UserPromptSubmit: ['running', '考え中…'], PreToolUse: ['running', '作業中…'], PermissionRequest: ['waiting', '入力待ち'], PostToolUseFailure: ['failed', 'エラー'], Stop: ['review', '完了'] };
    if (!Object.hasOwn(mapping, event)) return;
    let [state, message] = mapping[event];
    const directModel = recordedModel(data, []);
    const lines = !directModel || event === 'Stop'
      ? await transcriptTail(data.transcript_path) : [];
    const model = directModel || recordedModel(data, lines);
    if (event === 'Stop' && codexUsageLimited(lines)) [state, message] = ['sleeping', '寝ています'];
    let expression = 'normal';
    if (event === 'Stop' && state !== 'sleeping') {
      let text = data.last_assistant_message;
      if (typeof text !== 'string' && typeof data.transcript_path === 'string') {
        for (const entry of transcriptRecords(lines)) {
          try {
            const message = entry.type === 'response_item' ? entry.payload : entry.type === 'assistant' ? entry.message : null;
            if (!message || (entry.type === 'response_item' && (message.type !== 'message' || message.role !== 'assistant' || (message.phase && message.phase !== 'final_answer')))) continue;
            const content = message.content;
            text = typeof content === 'string' ? content : Array.isArray(content) ? content.filter(c => ['text', 'output_text'].includes(c.type)).map(c => c.text).join('\n') : '';
            break;
          } catch { /* Skip malformed message content. */ }
        }
      }
      const tail = typeof text === 'string' ? text.trimEnd().split(/\r?\n/).slice(-5).join('\n') : '';
      const marks = [...tail.matchAll(/\[表情:([^\]\r\n]*)\]/g)];
      const value = marks.at(-1)?.[1];
      if (['normal', 'smile', 'angry'].includes(value)) expression = value;
    }
    const index = process.argv.indexOf('--state-path');
    const path = index >= 0 ? process.argv[index + 1] : codexStatePath();
    if (!path) return;
    await fs.mkdir(dirname(path), { recursive: true });
    temporary = `${path}.${process.pid}.${Date.now()}.tmp`;
    await fs.writeFile(temporary, JSON.stringify({ state, expression, message, model, session_id: typeof data.session_id === 'string' ? data.session_id : '', updated_at: new Date().toISOString() }), { encoding: 'utf8', flag: 'wx' });
    await fs.rename(temporary, path);
  } catch { /* State IO failure must not affect Codex. */ }
  finally {
    if (temporary) await fs.unlink(temporary).catch(() => {});
    clearTimeout(deadline);
    finish();
  }
});

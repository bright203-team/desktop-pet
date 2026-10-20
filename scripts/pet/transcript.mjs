// Bound both IO and parsing; never search message text or tool arguments for models.
import { promises as fs } from 'node:fs';

export async function transcriptTail(path) {
  if (typeof path !== 'string') return [];
  let handle;
  try {
    handle = await fs.open(path, 'r');
    const stat = await handle.stat();
    if (!stat.isFile()) return [];
    const size = Math.min(stat.size, 2 * 1024 * 1024);
    const buffer = Buffer.alloc(size);
    const { bytesRead } = await handle.read(buffer, 0, size, stat.size - size);
    const lines = buffer.subarray(0, bytesRead).toString('utf8').split('\n');
    if (stat.size > size) lines.shift();
    return lines;
  } catch { return []; }
  finally { if (handle) await handle.close().catch(() => {}); }
}

function modelName(value) {
  return typeof value === 'string' && value.trim() && value.length <= 256 ? value : undefined;
}

export function* transcriptRecords(lines) {
  // Timers cannot interrupt synchronous JSON parsing. Leave time for state IO
  // and the other reader even when a bounded tail contains many broken lines.
  const deadline = performance.now() + 100;
  for (let i = lines.length - 1; i >= 0; i--) {
    if (performance.now() >= deadline) return;
    try {
      const entry = JSON.parse(lines[i]);
      if (entry && typeof entry === 'object' && !Array.isArray(entry)) yield entry;
    } catch { /* Incomplete JSONL lines are ignored. */ }
  }
}

export function recordedModel(data, lines) {
  const direct = modelName(data.model);
  if (direct) return direct;
  for (const entry of transcriptRecords(lines)) {
    const model = modelName(entry.model) ||
      (entry.type === 'assistant' && modelName(entry.message?.model)) ||
      (entry.type === 'turn_context' && modelName(entry.payload?.model));
    if (model) return model;
  }
}

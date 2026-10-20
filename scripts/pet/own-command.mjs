import { realpathSync } from 'node:fs';
import { resolve } from 'node:path';

// Windows may expose the same file via long/8.3 paths and different casing.
// Match only the exact known script and the flags our tools generate.
function canonical(path) {
  let result;
  try { result = realpathSync.native(path); } catch { result = resolve(path); }
  result = result.replaceAll('\\', '/');
  return process.platform === 'win32' ? result.toLowerCase() : result;
}
export function ownCommand(value, scripts) {
  if (typeof value !== 'string') return false;
  const match = /^node "([^"\r\n]+)"(?: --state-path "[^"\r\n]*")?(?: --created-event)?(?: --created-hooks)?$/.exec(value);
  return !!match && scripts.filter(Boolean).some(script => canonical(match[1]) === canonical(script));
}

import { posix, win32 } from 'node:path';
import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';

export function windowsToWsl(value) {
  const normalized = win32.normalize(value);
  if (!/^[a-z]:\\/i.test(normalized)) throw new Error('Expected Windows drive path');
  return `/mnt/${normalized[0].toLowerCase()}/${normalized.slice(3).replaceAll('\\', '/')}`;
}
export function codexStatePath({ env = process.env, platform = process.platform,
  release = () => readFileSync('/proc/sys/kernel/osrelease', 'utf8'),
  windowsLocal = () => execFileSync('cmd.exe', ['/d', '/c', 'echo %USERPROFILE%'],
    { encoding: 'utf8', timeout: 400, maxBuffer: 4096, windowsHide: true, stdio: ['ignore', 'pipe', 'ignore'] }).trim(),
} = {}) {
  if (env.CODEX_PET_STATE_PATH) return env.CODEX_PET_STATE_PATH;
  if (platform === 'win32') {
    if (!env.USERPROFILE) throw new Error('Set CODEX_PET_STATE_PATH or USERPROFILE');
    return win32.join(env.USERPROFILE, '.claude-desktop-pet', 'codex-state.json');
  }
  if (env.WSL_DISTRO_NAME || env.WSL_INTEROP || /microsoft/i.test(release())) {
    const local = env.USERPROFILE || windowsLocal();
    const root = local.startsWith('/mnt/') ? local : windowsToWsl(local);
    return posix.join(root, '.claude-desktop-pet', 'codex-state.json');
  }
  throw new Error('Use an explicit CODEX_PET_STATE_PATH outside Windows/WSL');
}

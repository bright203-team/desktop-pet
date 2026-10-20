// Explicit target required: this utility never silently chooses live settings.
import { readFileSync, writeFileSync, renameSync, unlinkSync } from 'node:fs';
import { codexStatePath } from './codex-path.mjs';
import { execFileSync } from 'node:child_process';
import { resolve } from 'node:path';
import { ownCommand } from './own-command.mjs';
import { fileURLToPath } from 'node:url';
const [action, argument, previousScript] = process.argv.slice(2);
const target = argument || process.env.CODEX_PET_SETTINGS_PATH;
const events = ['UserPromptSubmit', 'PreToolUse', 'PermissionRequest', 'PostToolUse', 'Stop'];
const script = fileURLToPath(new URL('codex-hook.mjs', import.meta.url)).replaceAll('\\', '/');
let temp;
try {
  if (!['add', 'remove'].includes(action) || !target) throw new Error('Usage: node scripts/pet/codex-settings.mjs add|remove <hooks.json>');
  // Avoid shell expansion in unusual installation paths.
  if (/["$`\r\n]/.test(script)) throw new Error('Unsupported hook path');
  let command = `node "${script}"`;
  const wsl = process.platform !== 'win32' && (process.env.WSL_DISTRO_NAME || process.env.WSL_INTEROP);
  if (wsl && action === 'add') {
    const path = codexStatePath({ windowsLocal: () => execFileSync('cmd.exe', ['/d', '/c', 'echo %USERPROFILE%'],
      { encoding: 'utf8', timeout: 10000, maxBuffer: 4096, windowsHide: true, stdio: ['ignore', 'pipe', 'ignore'] }).trim() });
    if (/["$`\r\n]/.test(path)) throw new Error('Unsupported state path');
    command += ` --state-path "${path}"`;
  }
  if (previousScript && /["$`\r\n]/.test(previousScript)) throw new Error('Unsupported previous hook path');
  let raw;
  try { raw = readFileSync(target, 'utf8'); } catch (error) { if (error.code !== 'ENOENT') throw error; raw = '{}'; }
  const settings = JSON.parse(raw.replace(/^\uFEFF/, ''));
  if (!settings || typeof settings !== 'object' || Array.isArray(settings)) throw new Error('Settings must be an object');
  if (settings.hooks !== undefined && (!settings.hooks || typeof settings.hooks !== 'object' || Array.isArray(settings.hooks))) throw new Error('Invalid hooks');
  for (const entries of Object.values(settings.hooks || {})) {
    if (!Array.isArray(entries) || entries.some(e => !e || !Array.isArray(e.hooks) || e.hooks.some(h => !h || typeof h !== 'object' || Array.isArray(h)))) throw new Error('Invalid hook entries');
  }
  const before = JSON.stringify(settings);
  const createdHooks = settings.hooks === undefined;
  const isOwn = value => ownCommand(value, [script, previousScript]);
  const hookCommand = h => isOwn(h.command) ? h.command :
    (typeof h.commandWindows === 'string' ? h.commandWindows.replace(/; exit \$LASTEXITCODE$/, '') : '');
  const isOwnedHook = h => h.type === 'command' && isOwn(hookCommand(h));
  let removeHooks = false;
  if (action === 'add') settings.hooks ??= {};
  for (const event of events) {
    const entries = settings.hooks?.[event] || [];
    if (action === 'add') {
      // Both development and installed registrations may exist. Merge only our
      // exact commands, retaining the provenance flags needed for clean removal.
      const owned = entries.flatMap(e => e.hooks).filter(isOwnedHook);
      if (owned.length > 1) {
        const first = owned[0];
        first.command = command + (owned.some(h => hookCommand(h).includes(' --created-event')) ? ' --created-event' : '') + (owned.some(h => hookCommand(h).includes(' --created-hooks')) ? ' --created-hooks' : '');
        settings.hooks[event] = entries.flatMap(entry => {
          const hooks = entry.hooks.filter(h => h === first || !isOwnedHook(h));
          return hooks.length === entry.hooks.length ? [entry] : hooks.length ? [{ ...entry, hooks }] : [];
        });
      }
      for (const entry of entries) for (const h of entry.hooks) {
        if (isOwnedHook(h)) {
          const current = hookCommand(h);
          h.command = command + (current.includes(' --created-event') ? ' --created-event' : '') +
            (current.includes(' --created-hooks') ? ' --created-hooks' : '');
          h.timeout = 5;
        }
      }
      if (!entries.some(e => e.hooks.some(h => isOwnedHook(h)))) {
        const createdEvent = settings.hooks[event] === undefined;
        (settings.hooks[event] ??= []).push({ hooks: [{ type: 'command', command: command + (createdEvent ? ' --created-event' : '') + (createdHooks ? ' --created-hooks' : ''), timeout: 5 }] });
      }
    } else if (settings.hooks?.[event]) {
      let createdEvent = false;
      settings.hooks[event] = entries.flatMap(entry => {
        for (const h of entry.hooks) {
          if (isOwnedHook(h)) {
            createdEvent ||= hookCommand(h).includes(' --created-event');
            removeHooks ||= hookCommand(h).includes(' --created-hooks');
          }
        }
        const hooks = entry.hooks.filter(h => !isOwnedHook(h));
        return hooks.length === entry.hooks.length ? [entry] : hooks.length ? [{ ...entry, hooks }] : [];
      });
      if (!settings.hooks[event].length && createdEvent) delete settings.hooks[event];
    }
  }
  // Windows uses PowerShell explicitly; keep the override in sync after migration.
  if (action === 'add' && process.platform === 'win32') {
    for (const entries of Object.values(settings.hooks)) for (const entry of entries) {
      for (const h of entry.hooks) if (isOwnedHook(h)) h.commandWindows = h.command + '; exit $LASTEXITCODE';
    }
  }
  if (removeHooks && Object.keys(settings.hooks).length === 0) delete settings.hooks;
  if (JSON.stringify(settings) !== before) {
    temp = `${resolve(target)}.${process.pid}.tmp`;
    writeFileSync(temp, JSON.stringify(settings, null, 2) + '\n', { encoding: 'utf8', flag: 'wx' });
    renameSync(temp, target);
  }
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
} finally {
  if (temp) try { unlinkSync(temp); } catch {}
}

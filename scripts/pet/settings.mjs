// Explicit target required: this utility never silently chooses live settings.
import { readFileSync, writeFileSync, renameSync, unlinkSync } from 'node:fs';
import { resolve } from 'node:path';
import { ownCommand } from './own-command.mjs';
import { fileURLToPath } from 'node:url';
const [action, argument, previousScript] = process.argv.slice(2);
const target = argument || process.env.CLAUDE_PET_SETTINGS_PATH;
const events = ['UserPromptSubmit', 'PreToolUse', 'PermissionRequest', 'Notification', 'PostToolUseFailure', 'Stop', 'StopFailure'];
const script = fileURLToPath(new URL('state-hook.mjs', import.meta.url)).replaceAll('\\', '/');
let temp;
try {
  if (!['add', 'remove'].includes(action) || !target) throw new Error('Usage: node scripts/pet/settings.mjs add|remove <settings.json>');
  // Avoid shell expansion in unusual installation paths.
  if (/["$`\r\n]/.test(script)) throw new Error('Unsupported hook path');
  const command = `node "${script}"`;
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
  let removeHooks = false;
  if (action === 'add') settings.hooks ??= {};
  const matchers = { Notification: 'permission_prompt|idle_prompt|elicitation_dialog', StopFailure: 'rate_limit|billing_error' };
  for (const event of events) {
    const entries = settings.hooks?.[event] || [];
    if (action === 'add') {
      // Both development and installed registrations may exist. Merge only our
      // exact commands, retaining the provenance flags needed for clean removal.
      const owned = entries.flatMap(e => e.hooks).filter(h => h.type === 'command' && isOwn(h.command));
      if (owned.length > 1) {
        const first = owned[0];
        first.command = command + (owned.some(h => h.command.includes(' --created-event')) ? ' --created-event' : '') + (owned.some(h => h.command.includes(' --created-hooks')) ? ' --created-hooks' : '');
        settings.hooks[event] = entries.flatMap(entry => {
          const hooks = entry.hooks.filter(h => h === first || !(h.type === 'command' && isOwn(h.command)));
          return hooks.length === entry.hooks.length ? [entry] : hooks.length ? [{ ...entry, hooks }] : [];
        });
      }
      for (const entry of entries) for (const h of entry.hooks) {
        if (h.type === 'command' && isOwn(h.command)) {
          h.command = command + (h.command.includes(' --created-event') ? ' --created-event' : '') + (h.command.includes(' --created-hooks') ? ' --created-hooks' : '');
        }
      }
      if (!entries.some(e => e.hooks.some(h => h.type === 'command' && isOwn(h.command)))) {
        const createdEvent = settings.hooks[event] === undefined;
        (settings.hooks[event] ??= []).push({ ...(matchers[event] ? { matcher: matchers[event] } : {}), hooks: [{ type: 'command', command: command + (createdEvent ? ' --created-event' : '') + (createdHooks ? ' --created-hooks' : ''), timeout: 5 }] });
      }
    } else if (settings.hooks?.[event]) {
      let createdEvent = false;
      settings.hooks[event] = entries.flatMap(entry => {
        for (const h of entry.hooks) {
          if (h.type === 'command' && isOwn(h.command)) {
            createdEvent ||= h.command.includes(' --created-event');
            removeHooks ||= h.command.includes(' --created-hooks');
          }
        }
        const hooks = entry.hooks.filter(h => !(h.type === 'command' && isOwn(h.command)));
        return hooks.length === entry.hooks.length ? [entry] : hooks.length ? [{ ...entry, hooks }] : [];
      });
      if (!settings.hooks[event].length && createdEvent) delete settings.hooks[event];
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

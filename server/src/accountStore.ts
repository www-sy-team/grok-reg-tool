/**
 * 账号记录存储。
 * registerBot 从 Python stdout 关联出 email/password/sso 后追加到这里。
 * 优先落盘到 DATA_DIR/accounts.json，保证 docker 环境重建后仍可保留；
 * 没有 DATA_DIR 时回退到 <cwd>/out/accounts.json 兼容旧行为。
 */
import { promises as fsp, existsSync } from 'node:fs';
import { join, resolve } from 'node:path';
import type { AccountRecord } from '@shared/runEvents';
import type { SsoCheckResult } from '@shared/ipc';

function accountsDir(): string {
  if (process.env.DATA_DIR) return resolve(process.env.DATA_DIR);
  return resolve(process.cwd(), 'out');
}

function accountsPath(): string {
  return join(accountsDir(), 'accounts.json');
}

async function readAll(): Promise<AccountRecord[]> {
  const path = accountsPath();
  if (!existsSync(path)) return [];
  try {
    const raw = await fsp.readFile(path, 'utf-8');
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as AccountRecord[]) : [];
  } catch {
    return [];
  }
}

export async function appendAccount(record: AccountRecord): Promise<void> {
  const dir = accountsDir();
  await fsp.mkdir(dir, { recursive: true });
  const all = await readAll();
  all.push(record);
  const path = accountsPath();
  const tmp = `${path}.tmp`;
  await fsp.writeFile(tmp, JSON.stringify(all, null, 2), 'utf-8');
  await fsp.rename(tmp, path);
}

export async function updateAccountSsoChecks(results: SsoCheckResult[]): Promise<void> {
  if (results.length === 0) return;
  const path = accountsPath();
  if (!existsSync(path)) return;

  const all = await readAll();
  const byId = new Map(results.map((r) => [r.id, r]));
  let changed = false;

  const next = all.map((account) => {
    const result = byId.get(account.id);
    if (!result) return account;
    changed = true;
    return {
      ...account,
      ssoAlive: result.alive,
      ssoStatus: result.status,
      ssoCheckedAt: result.checkedAt,
      ssoEmailConfirmed: result.emailConfirmed,
      ssoSessionTierId: result.sessionTierId,
      ssoCreateTime: result.createTime,
      ssoError: result.error,
    } satisfies AccountRecord;
  });

  if (!changed) return;
  const tmp = `${path}.tmp`;
  await fsp.writeFile(tmp, JSON.stringify(next, null, 2), 'utf-8');
  await fsp.rename(tmp, path);
}

export async function listAccounts(): Promise<AccountRecord[]> {
  const all = await readAll();
  return all.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}

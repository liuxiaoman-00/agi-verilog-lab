// 把 vlab-verifier MCP 服务走完 AGH 的「创建 → 信任 → 启用 → 校验」全流程。
// 每一步都可能在 TTY 上要一次 y 确认，所以统一用伪终端跑，并把回显落盘留证。
//
// 用法：node tools_agh_mcp_setup.mjs

import fs from 'node:fs';
import path from 'node:path';

const PTY_ROOT = process.env.AGH_PTY_ROOT
  || 'C:/Users/liumi/.workbuddy/binaries/node/workspace/node_modules/node-pty';
const { spawn } = await import(`file:///${PTY_ROOT}/lib/index.js`);

const PROJ = 'C:/Users/liumi/WorkBuddy/2026-10-02-20-04-02/agi-verilog-lab';
const HARNESS = 'C:/Users/liumi/WorkBuddy/2026-10-02-20-04-02/tools/agnes-harness';
const NODE24 = 'C:/Users/liumi/WorkBuddy/2026-10-02-20-04-02/tools/node24/node.exe';
const AGH = path.join(HARNESS, 'packages/cli/dist/local/agnes.mjs');
const LOGDIR = path.join(PROJ, 'runs');

const ALL = [];

function run(cwd, args, { sends = [], maxMs = 60000, tag = 'step' } = {}) {
  return new Promise((resolve) => {
    const out = [];
    const p = spawn(NODE24, [AGH, ...args], {
      cwd, cols: 160, rows: 50, env: { ...process.env, FORCE_COLOR: '0' },
    });
    p.onData((d) => { out.push(d); process.stdout.write(d); });

    let elapsed = 0, idx = 0;
    const timer = setInterval(() => {
      elapsed += 250;
      while (idx < sends.length && elapsed >= sends[idx].atMs) {
        process.stdout.write(`\n>>> [${tag} 发送] ${JSON.stringify(sends[idx].text)}\n`);
        p.write(sends[idx].text);
        idx++;
      }
      if (elapsed >= maxMs) { clearInterval(timer); p.kill(); }
    }, 250);

    p.onExit(({ exitCode }) => {
      clearInterval(timer);
      const text = out.join('');
      ALL.push({ tag, args, exitCode, text });
      fs.writeFileSync(path.join(LOGDIR, `_pty_${tag}.log`), text, 'utf8');
      resolve({ exitCode, text });
    });
  });
}

const Y = [{ atMs: 5000, text: 'y\r' }, { atMs: 14000, text: 'y\r' }];

function revision(text) {
  const m = text.match(/revision=([0-9a-f]{16,})/i)
    || text.match(/expected-revision\s+([0-9a-f]{16,})/i)
    || text.match(/"revision"\s*:\s*"([0-9a-f]{16,})"/i);
  return m ? m[1] : null;
}

console.log('\n===== 1) mcp get =====');
let r = await run(HARNESS, ['mcp', 'get', 'vlab-verifier'], { tag: 'mcp_get_1' });
let rev = revision(r.text);

if (!rev) {
  console.log('\n===== 1b) 用 list 兜底取 revision =====');
  r = await run(HARNESS, ['mcp', 'list'], { tag: 'mcp_list_1' });
  rev = revision(r.text);
}
console.log(`\n>>> 当前 revision = ${rev}`);

if (rev) {
  console.log('\n===== 2) mcp trust =====');
  await run(HARNESS, ['mcp', 'trust', 'vlab-verifier', '--expected-revision', rev],
    { sends: Y, tag: 'mcp_trust', maxMs: 70000 });

  console.log('\n===== 3) mcp get（取新 revision）=====');
  r = await run(HARNESS, ['mcp', 'get', 'vlab-verifier'], { tag: 'mcp_get_2' });
  const rev2 = revision(r.text) || rev;

  console.log('\n===== 4) mcp enable =====');
  await run(HARNESS, ['mcp', 'enable', 'vlab-verifier', '--expected-revision', rev2],
    { sends: Y, tag: 'mcp_enable', maxMs: 70000 });
}

console.log('\n===== 5) mcp status =====');
await run(HARNESS, ['mcp', 'status', 'vlab-verifier'], { tag: 'mcp_status' });

console.log('\n===== 6) mcp tools =====');
await run(HARNESS, ['mcp', 'tools', 'vlab-verifier'], { tag: 'mcp_tools' });

console.log('\n===== 7) mcp test =====');
await run(HARNESS, ['mcp', 'test', 'vlab-verifier'], { tag: 'mcp_test', maxMs: 90000 });

fs.writeFileSync(path.join(LOGDIR, '_pty_mcp_setup_all.json'),
  JSON.stringify(ALL, null, 2), 'utf8');
console.log('\n全部步骤完成，日志在 runs/_pty_*.log');

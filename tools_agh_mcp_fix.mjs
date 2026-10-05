// 重新走「取 revision → 启用 → 状态 → 连通测试 → 工具清单」，逐步留证。
// 用法：node tools_agh_mcp_fix.mjs

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

function run(args, { sends = [], maxMs = 70000, tag = 'step' } = {}) {
  return new Promise((resolve) => {
    const out = [];
    const p = spawn(NODE24, [AGH, ...args], {
      cwd: HARNESS, cols: 160, rows: 50,
      env: { ...process.env, FORCE_COLOR: '0' },
    });
    p.onData((d) => { out.push(d); process.stdout.write(d); });
    let elapsed = 0, idx = 0;
    const timer = setInterval(() => {
      elapsed += 250;
      while (idx < sends.length && elapsed >= sends[idx].atMs) {
        process.stdout.write(`\n>>> [${tag}] ${JSON.stringify(sends[idx].text)}\n`);
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

const Y = [{ atMs: 5000, text: 'y\r' }, { atMs: 15000, text: 'y\r' }];
const revOf = (t) => {
  const m = t.match(/revision=([0-9a-f]{16,})/i) || t.match(/"revision"\s*:\s*"([0-9a-f]{16,})"/i);
  return m ? m[1] : null;
};

console.log('\n===== get =====');
let r = await run(['mcp', 'get', 'vlab-verifier'], { tag: 'fix_get' });
let rev = revOf(r.text);
console.log(`\n>>> revision=${rev}`);

if (rev) {
  console.log('\n===== enable =====');
  await run(['mcp', 'enable', 'vlab-verifier', '--expected-revision', rev],
    { sends: Y, tag: 'fix_enable', maxMs: 90000 });

  console.log('\n===== status =====');
  await run(['mcp', 'status', 'vlab-verifier'], { tag: 'fix_status' });

  console.log('\n===== get（取新 revision）=====');
  r = await run(['mcp', 'get', 'vlab-verifier'], { tag: 'fix_get2' });
  const rev2 = revOf(r.text) || rev;

  console.log('\n===== test（真实连通）=====');
  await run(['mcp', 'test', 'vlab-verifier', '--expected-revision', rev2],
    { sends: Y, tag: 'fix_test', maxMs: 120000 });
}

console.log('\n===== tools =====');
await run(['mcp', 'tools', 'vlab-verifier'], { tag: 'fix_tools', maxMs: 90000 });

fs.writeFileSync(path.join(LOGDIR, '_pty_mcp_fix_all.json'),
  JSON.stringify(ALL, null, 2), 'utf8');
console.log('\n完成');

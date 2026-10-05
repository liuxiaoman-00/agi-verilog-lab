// 在伪终端里驱动 AGH 交互式 TUI 真实跑一次任务，全程回显落盘。
// 用法：node tools_agh_run_tui.mjs <mode>
//   mode=observe  只看启动界面（不发指令）
//   mode=run      发 /yolo + 任务指令

import fs from 'node:fs';
import path from 'node:path';

const PTY_ROOT = process.env.AGH_PTY_ROOT
  || 'C:/Users/liumi/.workbuddy/binaries/node/workspace/node_modules/node-pty';
const { spawn } = await import(`file:///${PTY_ROOT}/lib/index.js`);

const mode = process.argv[2] || 'observe';
const PROJ = 'C:/Users/liumi/WorkBuddy/2026-10-02-20-04-02/agi-verilog-lab';
const HARNESS = 'C:/Users/liumi/WorkBuddy/2026-10-02-20-04-02/tools/agnes-harness';
const NODE24 = 'C:/Users/liumi/WorkBuddy/2026-10-02-20-04-02/tools/node24/node.exe';
const AGH = path.join(HARNESS, 'packages/cli/dist/local/agnes.mjs');
const EDA_BIN = 'C:/Users/liumi/WorkBuddy/2026-10-02-20-04-02/tools/oss-cad-suite/bin';
const EDA_LIB = 'C:/Users/liumi/WorkBuddy/2026-10-02-20-04-02/tools/oss-cad-suite/lib';
const LOG = path.join(PROJ, 'runs', `_pty_tui_${mode}.log`);

const TASK = [
  '任务：用 Verilog 实现一个 4 位无符号数值比较器，模块名 cmp4，',
  '端口为 input [3:0] a, input [3:0] b, output gt, output eq, output lt，',
  '其中 gt 表示 a>b，eq 表示 a==b，lt 表示 a<b（注意是严格大于，不要写成 >=）。',
  '请按四步执行并真实动手，不要只给方案：',
  '第一步，简要说明你的设计思路；',
  '第二步，把 Verilog 代码写入本目录下的 agh_demo_cmp4.v；',
  '第三步，用 iverilog 编译并用 vvp 仿真验证，测试台要覆盖 a==b 这个边界；',
  '第四步，报告验证结论，如果验证失败就修改代码后重新验证。',
].join('');

// print 模式：一次性输出 + 在伪终端里应答审批（--park 会等待审批而不是直接放弃）
// yolo 模式：进 TUI 开一次「全权限」并保存，之后打印模式的新会话会继承该权限选择
const sends = mode === 'run'
  ? [
      { atMs: 12000, text: '/yolo\r' },
      { atMs: 22000, text: TASK + '\r' },
    ]
  : mode === 'yolo'
    ? [
        { atMs: 10000, text: '/yolo\r' },
        { atMs: 17000, text: '\r' },
      ]
    : mode === 'print'
      ? Array.from({ length: 40 }, (_, i) => ({ atMs: 15000 + i * 9000, text: 'y\r' }))
      : [];

const env = {
  ...process.env,
  FORCE_COLOR: '1',
  PATH: `${EDA_BIN};${EDA_LIB};${process.env.PATH}`,
};

// resume 模式：在「已开启全权限」的旧会话里继续跑，这样 shell 工具不再被审批拦住
const SID = process.env.AGH_SESSION_ID || '';
const args = mode === 'print'
  ? [AGH, '--cwd', PROJ, '-p', TASK, '--mode', 'text']
  : mode === 'resume'
    ? [AGH, 'resume', SID, '-p', TASK, '--mode', 'text']
    : [AGH, '--cwd', PROJ];

const log = fs.createWriteStream(LOG, { flags: 'w' });
const p = spawn(NODE24, args, {
  cwd: PROJ, cols: 170, rows: 60, env, name: 'xterm-256color',
});
p.onData((d) => { log.write(d); process.stdout.write(d); });

let elapsed = 0, idx = 0;
const maxMs = mode === 'observe' ? 26000 : mode === 'yolo' ? 30000 : 480000;
const timer = setInterval(() => {
  elapsed += 250;
  while (idx < sends.length && elapsed >= sends[idx].atMs) {
    process.stdout.write(`\n>>> [发送 ${idx}] ${sends[idx].text.slice(0, 60)}...\n`);
    p.write(sends[idx].text);
    idx++;
  }
  if (elapsed >= maxMs) { clearInterval(timer); p.kill(); }
}, 250);

p.onExit(({ exitCode }) => {
  clearInterval(timer);
  log.end();
  console.log(`\n--- TUI 退出 exitCode=${exitCode}，日志 ${LOG} ---`);
  process.exit(0);
});

// AGH 交互式会话的伪终端驱动器。
// AGH 的命令确认、/yolo 授权这些都要求真实 TTY，非交互管道会直接失败或挂住，
// 所以这里用 node-pty 开一个真终端，按时间线往里敲内容，并把全部回显落盘留证。
//
// 用法：
//   AGH_PTY_CFG=<配置文件路径> node agh_pty.mjs
//
// 配置文件字段：
//   { cwd, exe, args, log, sends:[{atMs, text}], maxMs, env }

// node-pty 装在隔离工作区里，ESM 不认 NODE_PATH，所以按绝对路径引入。
const PTY_ROOT = process.env.AGH_PTY_ROOT
  || 'C:/Users/liumi/.workbuddy/binaries/node/workspace/node_modules/node-pty';
const { spawn } = await import(`file:///${PTY_ROOT}/lib/index.js`);
import fs from 'node:fs';

const cfgPath = process.env.AGH_PTY_CFG;
if (!cfgPath) {
  console.error('AGH_PTY_CFG is required');
  process.exit(2);
}
const cfg = JSON.parse(fs.readFileSync(cfgPath, 'utf8'));

const log = fs.createWriteStream(cfg.log, { flags: 'w' });
const seen = [];

const env = { ...process.env, ...(cfg.env || {}) };
if (process.platform === 'win32') {
  // 强制 AGH 与 Web 走彩色/交互分支，输出更接近真实终端
  env.FORCE_COLOR = '1';
}

const p = spawn(cfg.exe, cfg.args, {
  cwd: cfg.cwd,
  cols: cfg.cols || 160,
  rows: cfg.rows || 50,
  env,
  name: 'xterm-256color',
});

p.onData((d) => {
  seen.push(d);
  log.write(d);
  if (cfg.echo !== false) process.stdout.write(d);
});

let elapsed = 0;
let idx = 0;
const tick = 250;
const timer = setInterval(() => {
  elapsed += tick;
  while (idx < cfg.sends.length && elapsed >= cfg.sends[idx].atMs) {
    const text = cfg.sends[idx].text;
    if (cfg.echo !== false) process.stdout.write(`\n>>> [发送] ${JSON.stringify(text)}\n`);
    p.write(text);
    idx++;
  }
  if (elapsed >= cfg.maxMs) {
    clearInterval(timer);
    p.kill();
  }
}, tick);

p.onExit(({ exitCode }) => {
  clearInterval(timer);
  log.end();
  console.log(`\n--- 进程退出 exitCode=${exitCode} 已写入 ${cfg.log} ---`);
  process.exit(0);
});

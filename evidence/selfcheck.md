# 元验证报告：先用已知缺陷校准裁判

- 参考实现自校准：13/13 通过
- 已知缺陷命中准确率：7/7

## A. 参考实现自校准（应为 PASS）

| 规格 | 向量数 | cell 数 | 结果 | 耗时(s) |
|---|---:|---:|---|---:|
| cmp4 | 256 | 3 | PASS | 1.16 |
| mux2v | 512 | 1 | PASS | 0.68 |
| add4 | 512 | 2 | PASS | 0.61 |
| dec38 | 16 | 2 | PASS | 0.55 |
| penc8 | 256 | 15 | PASS | 0.58 |
| bcdadd | 256 | 7 | PASS | 0.57 |
| alu4 | 2048 | 17 | PASS | 0.62 |
| posdet | 160 | 4 | PASS | 0.58 |
| sipo4 | 160 | 1 | PASS | 0.59 |
| cnt12 | 64 | 7 | PASS | 0.60 |
| seq1011 | 550 | 14 | PASS | 0.59 |
| traffic | 260 | 20 | PASS | 0.60 |
| unishift4 | 128 | 6 | PASS | 0.58 |

## B. 已知缺陷检出（应判为标注类别）

| 规格 | 注入缺陷 | 期望类别 | 实际类别 | 判定 | 说明 |
|---|---|---|---|---|---|
| cmp4 | 漏写右括号 | `SYNTAX` | `SYNTAX` | OK | C:\Users\liumi\WorkBuddy\2026-10-02-20-04-02\agi-verilog-lab\runs\_selfcheck\seeded_00_cmp4\attempt_0\cmp4.v:2: warning: timescale for cmp4 inherited from anoth |
| cmp4 | 端口位宽不符规格 | `INTERFACE` | `INTERFACE` | OK | 端口 `b` 位宽应为 4，实际为 3（[2:0]） |
| cmp4 | 边界语义写错 | `VALUE_MISMATCH` | `VALUE_MISMATCH` | OK | 16/256 个向量与参考不一致 |
| add4 | 组合逻辑分支不完整 | `LATCH` | `LATCH` | OK | 综合后推断出 4 个锁存器（组合逻辑不应有电平敏感器件） |
| posdet | 输出未寄存，早一拍 | `TIMING_SHIFT` | `TIMING_SHIFT` | OK | 输出相对参考超前 1 拍，平移对齐后命中 159/160，判定为节拍错位而非逻辑错误 |
| sipo4 | 移位方向反了 | `VALUE_MISMATCH` | `VALUE_MISMATCH` | OK | 110/160 个向量与参考不一致 |
| dec38 | 使能优先级错误 | `VALUE_MISMATCH` | `VALUE_MISMATCH` | OK | 8/16 个向量与参考不一致 |

# 真实跑批成绩单（Agnes 模型实测）

- 模型：agnes-3.0-flash（中国站 api.agnes-ai.cn/v1）
- 规格数：13

| 指标 | 数值 |
|---|---|
| 最终通过 | **12/13 = 92.3%** |
| 首次通过率 | **7/13 = 53.8%** |
| 平均尝试轮数 | 1.77 |
| 失败类别分布 | VALUE_MISMATCH×6, SYNTAX×4, TIMING_SHIFT×1 |
| 模型调用总次数 | 481 |
| 总耗时 | 3.8 分钟 |

## 逐题结果

| 规格 | 结果 | 尝试轮数 | 首次通过 | 最后一轮失败类别 | 耗时(s) |
|---|---|---|---|---|---|
| cmp4 | PASS | 1 | 是 | - | 9.9 |
| mux2v | PASS | 1 | 是 | - | 7.0 |
| add4 | PASS | 1 | 是 | - | 10.9 |
| dec38 | PASS | 2 | 否 | SYNTAX | 24.5 |
| penc8 | PASS | 2 | 否 | SYNTAX | 15.4 |
| bcdadd | FAIL | 4 | 否 | VALUE_MISMATCH | 33.7 |
| alu4 | PASS | 1 | 是 | - | 17.3 |
| posdet | PASS | 2 | 否 | SYNTAX | 22.2 |
| sipo4 | PASS | 1 | 是 | - | 6.2 |
| cnt12 | PASS | 1 | 是 | - | 10.4 |
| seq1011 | PASS | 4 | 否 | TIMING_SHIFT | 40.3 |
| traffic | PASS | 2 | 否 | VALUE_MISMATCH | 19.1 |
| unishift4 | PASS | 1 | 是 | - | 12.0 |

> 说明：本表由 `run.py --all` 自动生成。
> 原始数据：`runs/run_20261003_183630.json`；每一次模型调用留痕：`runs/model_journal.jsonl`。
> 唯一未通过项 bcdadd：模型习惯性实现为「经典 BCD 加法器」（输入按 0~9 处理），
> 与本规格「输入按 0~15 二进制相加后取个位」不一致 —— 属于裁判成功拦截的
> 「看似合理、实则不符规格」的典型案例，已如实保留而非调参放行。
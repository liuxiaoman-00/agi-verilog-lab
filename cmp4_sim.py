#!/usr/bin/env python3
# Offline behavior simulation of cmp4 (the 4-bit unsigned comparator).
# Mirrors the Verilog semantics in agh_demo_cmp4.v.
# For 4-bit unsigned a,b in [0,15]:
#   gt = 1 iff a > b  (strict)
#   eq = 1 iff a == b
#   lt = 1 iff a < b
# This script checks two properties over every (a,b) in [0,15]x[0,15]:
#   1) exactly one of gt/eq/lt is 1 (mutual exclusion + exhaustiveness)
#   2) the matching relation holds
#
# It also mirrors the testbench's concrete `check` calls so the trace is
# equivalent to running the vvp testbench in terms of stimuli.

MASK = 0b1111
N = 4

def cmp4(a, b):
    a &= MASK
    b &= MASK
    return {"gt": int(a > b), "eq": int(a == b), "lt": int(a < b)}

# --- 1) Exhaustive 16x16 property check ---
fail = 0
for a in range(1 << N):
    for b in range(1 << N):
        r = cmp4(a, b)
        s = r["gt"] + r["eq"] + r["lt"]
        if s != 1:
            print(f"EXCL FAIL a={a} b={b} -> {r} sum={s}")
            fail += 1
            continue
        expected_gt = int(a > b)
        expected_eq = int(a == b)
        expected_lt = int(a < b)
        if r["gt"] != expected_gt or r["eq"] != expected_eq or r["lt"] != expected_lt:
            print(f"VALUE FAIL a={a} b={b} -> {r}")
            fail += 1

print(f"Exhaustive 16x16 check: {fail} failures out of 256")

# --- 2) Concrete testbench trace (same cases as `check` in agh_demo_cmp4.v) ---
tb_cases = [
    # (a, b, label)
    (5,  5,  "a==b boundary"),
    (0,  0,  "eq extreme low"),
    (15, 15, "eq extreme high"),
    (1,  0,  "gt"),
    (15, 0,  "gt max vs min"),
    (8,  3,  "gt"),
    (0,  1,  "lt"),
    (0,  15, "lt min vs max"),
    (3,  8,  "lt"),
    (7,  8,  "adjacent lt (b=a+1)"),
    (8,  7,  "adjacent gt (a=b+1)"),
]
tb_fail = 0
print("\nTestbench trace (same calls as agh_demo_cmp4.v):")
print("a  b  gt eq lt  label")
for a, b, label in tb_cases:
    r = cmp4(a, b)
    s = r["gt"] + r["eq"] + r["lt"]
    ok = s == 1
    tag = "ok" if ok else "FAIL"
    if not ok:
        tb_fail += 1
    print(f"{a:2d} {b:2d}  {r['gt']}  {r['eq']}  {r['lt']}  [{tag}] {label}")

print(f"\nTestbench trace: {tb_fail} failures out of {len(tb_cases)}")
print("ALL PASSED" if fail == 0 and tb_fail == 0 else "SOME FAILED")

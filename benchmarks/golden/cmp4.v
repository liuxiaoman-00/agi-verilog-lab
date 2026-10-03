// 人工参考实现（golden），仅用于验证引擎的等价性比对，不参与 AI 生成。
module cmp4_golden (
    input  wire [3:0] a,
    input  wire [3:0] b,
    output wire       gt,
    output wire       eq,
    output wire       lt
);
  assign gt = (a > b);
  assign eq = (a == b);
  assign lt = (a < b);
endmodule

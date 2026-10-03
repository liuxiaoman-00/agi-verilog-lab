// 人工参考实现（golden）
module mux2v_golden (
    input  wire [3:0] in0,
    input  wire [3:0] in1,
    input  wire       sel,
    output wire [3:0] y
);
  assign y = sel ? in1 : in0;
endmodule

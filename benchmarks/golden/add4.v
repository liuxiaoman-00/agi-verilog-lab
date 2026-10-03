// 人工参考实现（golden）
module add4_golden (
    input  wire [3:0] a,
    input  wire [3:0] b,
    input  wire       cin,
    output wire [3:0] sum,
    output wire       cout
);
  wire [4:0] ext = a + b + cin;
  assign sum  = ext[3:0];
  assign cout = ext[4];
endmodule

// 人工参考实现（golden）：s = a + b（0..30），units = s mod 10，carry = (s >= 10)
module bcdadd_golden (
    input  wire [3:0] a,
    input  wire [3:0] b,
    output wire [3:0] units,
    output wire       carry
);
  wire [4:0] s = a + b;
  assign units = (s >= 5'd20) ? (s - 5'd20)
               : (s >= 5'd10) ? (s - 5'd10)
               :               s[3:0];
  assign carry = (s >= 5'd10);
endmodule

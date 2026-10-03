// 人工参考实现（golden）
module dec38_golden (
    input  wire       en,
    input  wire [2:0] addr,
    output wire [7:0] y
);
  assign y = en ? (8'h01 << addr) : 8'h00;
endmodule

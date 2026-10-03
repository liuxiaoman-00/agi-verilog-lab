// 人工参考实现（golden）：Moore 型寄存输出，滞后原序列一个 clk 周期
module posdet_golden (
    input  wire clk,
    input  wire rst_n,
    input  wire x,
    output reg  y
);
  reg x_d;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      x_d <= 1'b0;
      y   <= 1'b0;
    end else begin
      x_d <= x;
      y   <= x & ~x_d;
    end
  end
endmodule

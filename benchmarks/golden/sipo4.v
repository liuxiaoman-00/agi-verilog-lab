// 人工参考实现（golden）：每拍左移，din 从最低位串行移入
module sipo4_golden (
    input  wire clk,
    input  wire rst_n,
    input  wire din,
    output reg  [3:0] q
);
  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) q <= 4'h0;
    else        q <= {q[2:0], din};
  end
endmodule

// 人工参考实现（golden）
// mode: 00 保持 / 01 左移（si 进最低位）/ 10 右移（si 进最高位）/ 11 并行加载
module unishift4_golden (
    input  wire clk,
    input  wire rst_n,
    input  wire [1:0] mode,
    input  wire si,
    input  wire [3:0] d,
    output reg  [3:0] q
);
  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) q <= 4'h0;
    else case (mode)
      2'b01:   q <= {q[2:0], si};
      2'b10:   q <= {si, q[3:1]};
      2'b11:   q <= d;
      default: q <= q;
    endcase
  end
endmodule

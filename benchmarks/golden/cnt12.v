// 人工参考实现（golden）：load 优先级高于 en
module cnt12_golden (
    input  wire clk,
    input  wire rst_n,
    input  wire en,
    input  wire load,
    input  wire [3:0] d,
    output reg  [3:0] q
);
  always @(posedge clk or negedge rst_n) begin
    if (!rst_n)    q <= 4'd0;
    else if (load) q <= d;
    else if (en)   q <= (q == 4'd11) ? 4'd0 : q + 4'd1;
  end
endmodule

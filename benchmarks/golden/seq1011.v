// 人工参考实现（golden）：重叠式 1011 检测，y 为寄存输出
// cnt 表示当前已匹配到 1011 的前缀长度；nxt 为下一状态
module seq1011_golden (
    input  wire clk,
    input  wire rst_n,
    input  wire x,
    output reg  y
);
  reg [2:0] cnt;
  reg [2:0] nxt;

  always @(*) begin
    case (cnt)
      3'd0: nxt = x ? 3'd1 : 3'd0;   // 前缀 ""
      3'd1: nxt = x ? 3'd1 : 3'd2;   // 前缀 "1"
      3'd2: nxt = x ? 3'd3 : 3'd0;   // 前缀 "10"
      3'd3: nxt = x ? 3'd4 : 3'd2;   // 前缀 "101"
      3'd4: nxt = x ? 3'd1 : 3'd2;   // 已匹配，回退到最长可行后缀
      default: nxt = 3'd0;
    endcase
  end

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      cnt <= 3'd0;
      y   <= 1'b0;
    end else begin
      cnt <= nxt;
      y   <= (nxt == 3'd4);
    end
  end
endmodule

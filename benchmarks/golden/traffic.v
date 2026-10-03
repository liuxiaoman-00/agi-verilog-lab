// 人工参考实现（golden）
// 红=2'd0 黄=2'd1 绿=2'd2；时长：绿 5、黄 2、红 4 个 clk 周期
module traffic_golden (
    input  wire clk,
    input  wire rst_n,
    output reg  [1:0] light
);
  localparam RED    = 2'd0;
  localparam YELLOW = 2'd1;
  localparam GREEN  = 2'd2;

  reg [2:0] t;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      light <= GREEN;
      t     <= 3'd0;
    end else begin
      case (light)
        GREEN:  if (t == 3'd4) begin light <= YELLOW; t <= 3'd0; end
                else                begin              t <= t + 3'd1; end
        YELLOW: if (t == 3'd1) begin light <= RED;    t <= 3'd0; end
                else                begin              t <= t + 3'd1; end
        default: if (t == 3'd3) begin light <= GREEN; t <= 3'd0; end
                 else                begin             t <= t + 3'd1; end
      endcase
    end
  end
endmodule

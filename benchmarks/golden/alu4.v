// 人工参考实现（golden）
module alu4_golden (
    input  wire [3:0] a,
    input  wire [3:0] b,
    input  wire [2:0] op,
    output reg  [3:0] y,
    output wire       zero
);
  always @(*) begin
    case (op)
      3'b000:  y = a + b;
      3'b001:  y = a - b;
      3'b010:  y = a & b;
      3'b011:  y = a | b;
      3'b100:  y = a ^ b;
      3'b101:  y = {a[2:0], 1'b0};
      3'b110:  y = ~a;
      default: y = (a < b) ? 4'h1 : 4'h0;
    endcase
  end
  assign zero = (y == 4'h0);
endmodule

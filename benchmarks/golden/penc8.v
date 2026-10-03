// 人工参考实现（golden）：优先级 din[7] 最高，din[0] 最低
module penc8_golden (
    input  wire [7:0] din,
    output reg  [2:0] code,
    output reg        valid
);
  always @(*) begin
    valid = 1'b0;
    code  = 3'd0;
    if      (din[7]) begin code = 3'd7; valid = 1'b1; end
    else if (din[6]) begin code = 3'd6; valid = 1'b1; end
    else if (din[5]) begin code = 3'd5; valid = 1'b1; end
    else if (din[4]) begin code = 3'd4; valid = 1'b1; end
    else if (din[3]) begin code = 3'd3; valid = 1'b1; end
    else if (din[2]) begin code = 3'd2; valid = 1'b1; end
    else if (din[1]) begin code = 3'd1; valid = 1'b1; end
    else if (din[0]) begin code = 3'd0; valid = 1'b1; end
  end
endmodule

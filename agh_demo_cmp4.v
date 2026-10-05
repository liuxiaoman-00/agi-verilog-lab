// 4-bit unsigned comparator
module cmp4 (
    input  [3:0] a,
    input  [3:0] b,
    output       gt,   // a > b  (strict)
    output       eq,   // a == b
    output       lt    // a < b
);

    assign gt = (a > b);
    assign eq = (a == b);
    assign lt = (a < b);

endmodule

`ifdef CMP4_TB

`timescale 1ns / 1ps

module cmp4_tb;

    reg  [3:0] a, b;
    wire       gt, eq, lt;

    cmp4 dut (
        .a(a),
        .b(b),
        .gt(gt),
        .eq(eq),
        .lt(lt)
    );

    integer errors = 0;

    task check(input [3:0] ra, input [3:0] rb);
        begin
            a = ra; b = rb;
            #2;
            if (ra > rb && gt !== 1'b1) begin
                errors = errors + 1;
                $display("FAIL [%0d vs %0d] expected gt=1, got %b (eq=%b lt=%b)", ra, rb, gt, eq, lt);
            end
            if (ra < rb && lt !== 1'b1) begin
                errors = errors + 1;
                $display("FAIL [%0d vs %0d] expected lt=1, got %b (gt=%b eq=%b)", ra, rb, lt, gt, eq);
            end
            if (ra == rb && eq !== 1'b1) begin
                errors = errors + 1;
                $display("FAIL [%0d vs %0d] expected eq=1, got %b (gt=%b lt=%b)", ra, rb, eq, gt, lt);
            end
            // mutual exclusion: exactly one of gt/eq/lt must be 1
            if ((gt + eq + lt) !== 2'd1) begin
                errors = errors + 1;
                $display("FAIL [%0d vs %0d] outputs not mutually exclusive: gt=%b eq=%b lt=%b",
                         ra, rb, gt, eq, lt);
            end
        end
    endtask

    initial begin
        // a == b boundary (critical case)
        check(4'd5, 4'd5);
        // more equality cases
        check(4'd0, 4'd0);
        check(4'd15, 4'd15);
        // a > b
        check(4'd1, 4'd0);
        check(4'd15, 4'd0);
        check(4'd8, 4'd3);
        // a < b
        check(4'd0, 4'd1);
        check(4'd0, 4'd15);
        check(4'd3, 4'd8);
        // adjacent cases around equality
        check(4'd7, 4'd8);  // lt
        check(4'd8, 4'd7);  // gt

        #4;
        if (errors == 0)
            $display("ALL TESTS PASSED");
        else
            $display("%0d TESTS FAILED", errors);
        $finish;
    end

endmodule

`endif

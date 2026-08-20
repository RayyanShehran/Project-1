`timescale 1ns/1ps

module adder_tb;

    localparam int WIDTH = 8;

    logic [WIDTH-1:0] a, b, sum;
    logic             carry_out;
    int               errors = 0;

    // Instantiate the design under test.
    adder #(.WIDTH(WIDTH)) dut (
        .a         (a),
        .b         (b),
        .sum       (sum),
        .carry_out (carry_out)
    );

    // Drive one vector, compare against an independently computed answer.
    task automatic check(input logic [WIDTH-1:0] ta, tb);
        logic [WIDTH:0] expected;
        a = ta;
        b = tb;
        #1;                      // let the logic settle
        expected = ta + tb;      // WIDTH+1 bits, so nothing truncates
        if ({carry_out, sum} !== expected) begin
            $display("FAIL: %0d + %0d gave %0d, expected %0d",
                     ta, tb, {carry_out, sum}, expected);
            errors = errors + 1;
        end
    endtask

    initial begin
        $dumpfile("waveform.vcd");
        $dumpvars(0, adder_tb);

        check(8'd0,   8'd0);
        check(8'd1,   8'd1);
        check(8'd255, 8'd1);      // rolls over
        check(8'd200, 8'd100);    // carry out
        check(8'd127, 8'd128);

        for (int i = 0; i < 50; i++) begin
            check($urandom_range(0, 255), $urandom_range(0, 255));
        end

        if (errors == 0) begin
            $display("PASS");
            $finish;              // exit 0
        end else begin
            $display("FAIL: %0d errors", errors);
            $fatal(1);            // exit non-zero
        end
    end

endmodule
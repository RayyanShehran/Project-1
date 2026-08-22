`timescale 1ns/1ps

module counter_tb;

    localparam int  WIDTH      = 4;
    localparam time CLK_PERIOD = 10ns;

    logic             clk = 1'b0;
    logic             rst_n;
    logic             enable;
    logic [WIDTH-1:0] count;

    logic [WIDTH-1:0] expected;    // reference model
    int               errors = 0;

    counter #(.WIDTH(WIDTH)) dut (
        .clk    (clk),
        .rst_n  (rst_n),
        .enable (enable),
        .count  (count)
    );

    // ---- Clock generator: toggles forever ----
    always #(CLK_PERIOD/2) clk = ~clk;

    // ---- Watchdog: kill the sim if it hangs ----
    initial begin
        #(CLK_PERIOD * 1000);
        $display("FAIL: timeout, simulation did not finish");
        $fatal(1);
    end

    // ---- Advance exactly one clock, then settle ----
    // Drive inputs and sample outputs ONLY after calling this.
    // Never on the edge itself.
    task automatic tick();
        @(posedge clk);
        #1;
    endtask

    task automatic check(input string label);
        if (count !== expected) begin
            $display("FAIL [%s] at %0t: count=%0d expected=%0d",
                     label, $time, count, expected);
            errors = errors + 1;
        end
    endtask

    initial begin
        $dumpfile("waveform.vcd");
        $dumpvars(0, counter_tb);

        // --- Reset sequence ---
        rst_n    = 1'b0;
        enable   = 1'b0;
        expected = '0;
        tick();
        tick();
       check("during reset");

        // --- Release reset, still disabled ---
        rst_n = 1'b1;
        tick();
        check("reset released, enable low");

        // --- Count up, past the wrap point ---
        enable = 1'b1;
        for (int i = 0; i < 40; i++) begin
            tick();
            expected = expected + 1'b1;   // reference model tracks in lockstep
            check("counting");
        end

        // --- Disable and confirm it holds ---
        enable = 1'b0;
        for (int i = 0; i < 5; i++) begin
            tick();
            check("holding");
        end

        // --- Reset mid-count ---
        rst_n = 1'b0;
        tick();
        expected = '0;
        check("reset while counting");

        if (errors == 0) begin
            $display("PASS");
            $finish;
        end else begin
            $display("FAIL: %0d errors", errors);
            $fatal(1);
        end
    end

endmodule
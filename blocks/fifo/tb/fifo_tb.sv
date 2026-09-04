`timescale 1ns/1ps

module fifo_tb #(
    parameter int WIDTH = 8,
    parameter int DEPTH = 4
);

    localparam time CLK_PERIOD = 10ns;

    logic clk = 1'b0;
    logic arst_n;
    logic wr_en;
    logic rd_en;
    logic [WIDTH-1:0] din;
    logic [WIDTH-1:0] dout;
    logic full;
    logic empty;

    logic [WIDTH-1:0] expected_queue[$];
    logic [WIDTH-1:0] expected_dout;
    int errors = 0;

    fifo #(
        .WIDTH(WIDTH),
        .DEPTH(DEPTH)
    ) dut (
        .clk   (clk),
        .arst_n(arst_n),
        .wr_en (wr_en),
        .rd_en (rd_en),
        .din   (din),
        .dout  (dout),
        .full  (full),
        .empty (empty)
    );

    always #(CLK_PERIOD / 2) clk = ~clk;

    initial begin
        #(CLK_PERIOD * 1000);
        $display("FAIL: timeout");
        $fatal(1);
    end

    task automatic tick();
        @(posedge clk);
        #1;
    endtask

    task automatic check_flags(input string label);
        if (empty !== (expected_queue.size() == 0)) begin
            $display("FAIL [%s]: empty=%0b expected=%0b",
                     label, empty, expected_queue.size() == 0);
            errors++;
        end

        if (full !== (expected_queue.size() == DEPTH)) begin
            $display("FAIL [%s]: full=%0b expected=%0b",
                     label, full, expected_queue.size() == DEPTH);
            errors++;
        end
    endtask

    task automatic do_write(input logic [WIDTH-1:0] value);
        wr_en = 1'b1;
        rd_en = 1'b0;
        din = value;

        tick();

        if (expected_queue.size() < DEPTH) begin
            expected_queue.push_back(value);
        end

        wr_en = 1'b0;
        check_flags("write");
    endtask

    task automatic do_read();
        wr_en = 1'b0;
        rd_en = 1'b1;

        if (expected_queue.size() > 0) begin
            expected_dout = expected_queue.pop_front();
        end

        tick();

        if (dout !== expected_dout) begin
            $display("FAIL [read]: dout=%0d expected=%0d", dout, expected_dout);
            errors++;
        end

        rd_en = 1'b0;
        check_flags("read");
    endtask

    initial begin
        $dumpfile("work/fifo/icarus/waveform.vcd");
        $dumpvars(0, fifo_tb);

        arst_n = 1'b0;
        wr_en = 1'b0;
        rd_en = 1'b0;
        din = '0;
        expected_dout = '0;

        tick();
        tick();

        arst_n = 1'b1;
        tick();
        check_flags("after reset");

        do_write(8'd10);
        do_write(8'd20);
        do_write(8'd30);
        do_write(8'd40);
        check_flags("full");

        do_write(8'd99); // should be ignored because FIFO is full

        do_read();
        do_read();

        do_write(8'd50);
        do_write(8'd60);

        do_read();
        do_read();
        do_read();
        do_read();
        check_flags("empty");

        do_read(); // should be ignored because FIFO is empty

        if (errors == 0) begin
            $display("PASS");
            $finish;
        end else begin
            $display("FAIL: %0d errors", errors);
            $fatal(1);
        end
    end

endmodule

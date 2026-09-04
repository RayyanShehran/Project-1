`timescale 1ns/1ps

module fifo #(
    parameter int WIDTH = 8,
    parameter int DEPTH = 4
) (
    input  logic             clk,
    input  logic             arst_n,
    input  logic             wr_en,
    input  logic             rd_en,
    input  logic [WIDTH-1:0] din,
    output logic [WIDTH-1:0] dout,
    output logic             full,
    output logic             empty
);

    localparam int ADDR_WIDTH = $clog2(DEPTH);

    logic [WIDTH-1:0] mem [DEPTH];
    logic [ADDR_WIDTH-1:0] wr_ptr;
    logic [ADDR_WIDTH-1:0] rd_ptr;
    logic [ADDR_WIDTH:0]   count;

    assign full  = (count == (ADDR_WIDTH + 1)'(DEPTH));
    assign empty = (count == '0);

    always_ff @(posedge clk or negedge arst_n) begin
        if (!arst_n) begin
            wr_ptr <= '0;
            rd_ptr <= '0;
            count  <= '0;
            dout   <= '0;
        end else begin
            if (wr_en && !full) begin
                mem[wr_ptr] <= din;
                wr_ptr <= wr_ptr + 1'b1;
            end

            if (rd_en && !empty) begin
                dout <= mem[rd_ptr];
                rd_ptr <= rd_ptr + 1'b1;
            end

            if ((wr_en && !full) && !(rd_en && !empty)) begin
                count <= count + 1'b1;
            end else if ((rd_en && !empty) && !(wr_en && !full)) begin
                count <= count - 1'b1;
            end
        end
    end

endmodule

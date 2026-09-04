`timescale 1ns/1ps

module counter #(
    parameter int WIDTH = 8
) (
    input  logic             clk,
    input  logic             arst_n,    // asynchronous, active low
    input  logic             enable,
    output logic [WIDTH-1:0] count
);

    always_ff @(posedge clk or negedge arst_n) begin
        if (!arst_n)
            count <= '0;
        else if (enable)
            count <= count + 1'b1;
        // else: hold. No assignment means the flop keeps its value.
    end

endmodule

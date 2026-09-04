`timescale 1ns/1ps

module adder #(
    parameter int WIDTH = 8
) (
    input  logic [WIDTH-1:0] a,
    input  logic [WIDTH-1:0] b,
    output logic [WIDTH-1:0] sum,
    output logic             carry_out
);

    // Concatenating carry_out with sum makes a WIDTH+1 bit target,
    // so the carry has somewhere to land instead of being truncated.
    assign {carry_out, sum} = a + b;

endmodule

module counter #(
    parameter int WIDTH = 8
) (
    input  logic             clk,
    input  logic             rst_n,     // synchronous, active low
    input  logic             enable,
    output logic [WIDTH-1:0] count
);

    always_ff @(posedge clk) begin
        if (!rst_n)
            count <= '0;
        else if (enable)
            count <= count + 1'b1;
        // else: hold. No assignment means the flop keeps its value.
    end

endmodule
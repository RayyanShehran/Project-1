# Adopt External RTL

Use this when RTL is outside `blocks/` or does not yet have a hand-written
`block.yaml`.

Commands:

```bash
rtlflow adopt path/to/rtl
rtlflow adopt path/to/rtl --write-config .rtlflow/adopted/decoder/block.yaml
rtlflow adopt path/to/rtl --run --flow lint_only
rtlflow run --config .rtlflow/adopted/decoder/block.yaml --flow lint_only
```

What adoption infers:

- Source files from an existing `.f` file, or by walking for `.sv` and `.v`.
- Candidate top modules from module instantiation relationships.
- Testbench modules using the no-ports-plus-instantiates-top heuristic.
- Include directories containing `.svh` files.

Common failures:

- Ambiguous top modules are reported with candidates instead of guessed.
- No testbench is acceptable for `lint_only`; simulation stages may be skipped.
- Generated configs write a sibling `files.f` next to `block.yaml`.

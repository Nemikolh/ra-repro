# rust-analyzer: Find All References hangs because of a markdown file

Find All References on a plain function hangs (the server pins the CPU) when the crate directory contains a particular `.md` file.

The markdown file is not referenced by any Rust code.

Renaming it to `.txt` makes the same request answer instantly.


## Layout

```
src/main.rs           calls serve::idle::decide()
src/serve/idle.rs     pub fn decide() {}
docs/notes.md         the trigger (anonymized text, one occurrence of "decide")
find-refs.py          minimal LSP client that times the request
```


## Reproduce

Requires Python 3 and a `rust-analyzer` binary.

```sh
python3 find-refs.py                          # rust-analyzer on PATH
python3 find-refs.py /path/to/rust-analyzer   # or a specific binary
```

The script starts rust-analyzer on this crate, waits until it is idle, then sends `textDocument/references` on `decide` in `src/serve/idle.rs`.

It kills the server after 10 seconds.

**Hangs:**

```
$ python3 find-refs.py
HANG: no answer to textDocument/references within 10s
```

**Same content, different extension:**

```
$ mv docs/notes.md docs/notes.txt
$ python3 find-refs.py
OK: 2 references in 0.00s
```


## Versions

Reproduced on Linux x86_64 with:

- `rust-analyzer 1.98.0 (88d9e12 2026-08-18)` (rustup component)
- `rust-analyzer 0.3.3081-standalone` (VS Code extension)


## Notes

- Indexing finishes normally (a few seconds). Only the references request hangs.
- No individual profiled step completes while it hangs (`RA_PROFILE='*>200'`), so it looks stuck in a single operation rather than slow.
- Found in a real project where an agent's session log (markdown) lived in the repository. Bisecting that log produced `docs/notes.md`.

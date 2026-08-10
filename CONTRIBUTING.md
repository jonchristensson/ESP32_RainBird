# Contributing

Thanks for your interest in improving this project. It's a small, single-board
firmware project, so the process is intentionally lightweight.

## Development approach

Changes are planned as small, self-contained proposals before any code is
written, then broken into independently workable, vertical-slice pieces of
work — each one a complete change end-to-end (code, docs, and verification
steps) rather than a partial layer of a larger change. This keeps pull
requests reviewable and keeps the firmware safe to flash at every step.

If you're proposing a nontrivial change (new sensor input, new threshold
logic, a new communication path), consider opening an issue first to describe
the problem and your proposed approach before sending a pull request. Small
fixes (typos, doc corrections, obvious bugs) can go straight to a PR.

## Commit convention

Commit messages use the prefix:

```
[short-topic-name/NN] description
```

Where `short-topic-name` identifies the initiative or area of the codebase
the change belongs to, and `NN` is a sequence number if the change is one of
several related commits. A single commit should not mix unrelated changes.

Example:

```
[wifi-resilience/02] Add exponential backoff to reconnect loop
```

## Code style

- MicroPython-compatible Python for anything that runs on the device
  (`boot.py`, `main.py`, and the modules they import). Standard CPython is
  fine for host-side tools in `tools/`.
- Keep the fail-open design intact: any change to `irrigation.py`, `wifi.py`,
  or `main.py` must preserve the property that loss of power, WiFi, or an
  unhandled exception leaves the relay de-energized (irrigation allowed).
- No new required cloud dependencies. Optional integrations (like the
  Google Sheets logger) must degrade gracefully when unconfigured.

## Testing

There's no CI for this project — verification is manual, on real hardware:

- `tools/test_api.py` checks the weather API call and parsing logic from a
  desktop Python environment before anything touches the device.
- Serial output (`mpremote connect <port> repl`) is the primary way to
  confirm firmware behavior after flashing.
- Changes to relay/threshold logic should be bench-tested with a multimeter
  on the relay's NC/COM terminals before being considered done — see
  `docs/instructions/03-wiring.html` for the bench test procedure.

## Pull requests

- Keep PRs focused on one change.
- Describe what you tested and how (serial output, bench test results, etc.).
- If your change touches `secrets_template.py`, do not include real
  credentials anywhere in the diff.

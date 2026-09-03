# Style examples from `cli.py`

Read this when the SKILL.md rule is not enough. Copy the shape, not the
domain logic.

## Log helpers

```python
def _prefix() -> Text:
    return Text("setup-spyder", style="bold cyan")


def log(message: str) -> None:
    console.print(Text.assemble(_prefix(), "  ", (message, "white")), soft_wrap=True)


def log_kv(key: str, value: object) -> None:
    console.print(
        Text.assemble(
            _prefix(),
            "    ",
            (f"{key}: ", "dim cyan"),
            (str(value), "bold white"),
        ),
        soft_wrap=True,
    )
```

## Late import + expected failure

```python
    try:
        import spyder
        import spyder_kernels
    except ImportError as exc:
        log_error(f"missing dependency ({exc}).")
        log("In the other repository, add this package:")
        log_kv("install", f"uv add git+{REPO_URL}")
        return 1
```

## Keyword-only API + Path resolve

```python
    workdir = Path(workdir).resolve() if workdir else Path.cwd().resolve()
```

## argparse remainder

```python
    parser.add_argument(
        "spyder_args",
        nargs=argparse.REMAINDER,
        help="Extra arguments forwarded to Spyder (after --).",
    )
```

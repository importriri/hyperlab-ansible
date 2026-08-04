# Choices panel

Every open HyperLab decision lives in one source file, with its active value,
alternatives, consequences and affected paths. This prevents hidden defaults and
keeps the rendered documentation aligned with the code.

Open `docs/choices.html`; it is self-contained and has no external resources.

```bash
python3 tools/choices/choices.py check
python3 tools/choices/choices.py vars > group_vars/all/choices.yml
python3 tools/choices/choices.py panel docs/choices.html
python3 tools/choices/choices.py set desktop_palette blue
```

The consistency test compares declared decisions with their implementation. A
choice that no longer describes the code fails verification.

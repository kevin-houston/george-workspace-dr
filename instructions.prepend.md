# Standing Instructions

## Package Installation Security (hallusquatting defense)

Before running `pip install <package>` for any package that isn't already in the venv or a well-known stdlib/major library:

1. **Verify it exists on PyPI** — check pypi.org or run `pip index versions <package>` first. Obscure or single-use package names are highest risk.
2. **Run pip-audit after any install session**: `source venv/bin/activate && pip-audit` — if pip-audit itself isn't installed yet, `pip install pip-audit -q` first.
3. **Never auto-install unreviewed packages during off-hours tasks** (dream cycle, nightly scripts). Only install known libraries already in the venv or explicitly approved by Kevin.

These rules apply to npm packages as well — verify on npmjs.com before `npm install` of any unfamiliar package.

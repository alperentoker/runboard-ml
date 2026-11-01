# Releasing

runboard is published on PyPI as **runboard-ml** (the name `runboard` belongs to another project). A version tag
publishes it: `.github/workflows/publish.yml` checks that the tag matches `pyproject.toml`, runs the tests, builds the
sdist and the wheel, and uploads them with PyPI's trusted publishing, so no token is kept in the repository or in
GitHub secrets.

## Once: let PyPI trust this repository

1. Sign in at <https://pypi.org> (two-factor authentication is required).
2. *Your account → Publishing → Add a new pending publisher*, GitHub tab:
   - PyPI project name: `runboard-ml`
   - Owner: `alperentoker`, repository: `runboard-ml`
   - Workflow name: `publish.yml`
   - Environment name: `pypi`
3. On GitHub, *Settings → Environments → New environment* `pypi` (optionally: *Required reviewers* yourself, so each
   release waits for your click).

## Each release

1. Set the version in `pyproject.toml` and `runboard/__init__.py`, and give the CHANGELOG section its number and date.
2. Commit and push, then tag and push the tag:

   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```

3. Follow *Actions → publish*. When it is green, <https://pypi.org/project/runboard-ml/> has the release and
   `pip install runboard-ml` installs it.

A version can be published only once: to fix a broken release, publish the next number.

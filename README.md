<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="dark_mode.svg?v=12">
    <source media="(prefers-color-scheme: light)" srcset="light_mode.svg?v=12">
    <img src="light_mode.svg?v=12" alt="Karthik Subramanian's GitHub Profile">
  </picture>
</div>

## Profile card updater

`survey.py` refreshes the SVG stats (contributions, repos, age, Berkeley weather) daily via GitHub Actions.

### Local run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ACCESS_TOKEN=ghp_...   # PAT with repo + read:user
export USER_NAME=KarthikSubramanian07
python survey.py
python -m unittest discover -s tests -v
```

### Secrets

| Secret | Purpose |
|--------|---------|
| `ACCESS_TOKEN` | GitHub PAT used by GraphQL (`repo` + `read:user`) |
| `USER_NAME` | GitHub login (defaults to `KarthikSubramanian07` if unset in local runs) |

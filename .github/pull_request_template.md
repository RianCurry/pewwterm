## Summary

Describe the user-visible change and why it is needed.

## Changes

- 
- 

## Testing

Commands run and their actual results:

```text
.venv/bin/pytest -q
...

ruff check src tests demo/capture_screens.py
...
```

## Documentation

- [ ] README updated for user-visible behaviour
- [ ] Relevant `docs/` page updated
- [ ] Help screen updated for new or changed shortcuts
- [ ] No documentation change needed

## Checklist

- [ ] The change is focused and does not include unrelated formatting churn
- [ ] Python 3.10 compatibility is preserved
- [ ] New or changed behaviour has a regression test
- [ ] External programs use argument lists, no shell and bounded timeouts
- [ ] Missing optional tools degrade gracefully
- [ ] No secrets, private paths, media or cache files are included
- [ ] `pytest` and `ruff` pass locally

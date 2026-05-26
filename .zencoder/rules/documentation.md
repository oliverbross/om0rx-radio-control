# Documentation Organization Rules

## Documentation Location

Maintained project documentation belongs in `/docs`.

### Applies To

- Project guides and README-style references
- Implementation notes that are still current
- Architecture documentation
- API documentation
- Testing documentation
- Deployment or startup guides

### Exceptions

- Root-level `README.md`
- Root-level project metadata such as `LICENSE`
- `.zencoder/rules/*.md` files

### Directory Structure

```text
docs/
├── PROJECT_REVIEW.md      Current architecture review and next work
└── archive/               Historical notes and diagnostics
```

### When Creating Documentation

1. Place maintained docs under `docs/`.
2. Use `docs/archive/` for historical notes that should not guide current work.
3. Keep root clean; do not add one-off summaries or reports there.
4. Update existing docs in place instead of duplicating them.

## Example Commands

When creating maintained documentation, use paths like:

- `C:\Projects\om0rx-radio-control\docs\FEATURE_NAME.md`
- Not: `C:\Projects\om0rx-radio-control\FEATURE_NAME.md`

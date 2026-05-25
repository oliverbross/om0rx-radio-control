# Documentation Organization Rules

## Documentation Location

**All documentation files MUST be placed in the `/documentation` folder.**

### Applies to:
- All `.md` files (Markdown documentation)
- All `.txt` files (Markdown documentation)
- Project guides and README files
- Implementation summaries
- Technical documentation
- User guides and tutorials
- Architecture documentation
- API documentation
- Change logs and update notes
- Testing documentation
- Deployment guides

### Exceptions:
- Root-level `README.md` (if serves as project entry point)
- `LICENSE.md` or `LICENSE` files
- `.zencoder/rules/*.md` files (Zencoder configuration)

### Directory Structure:
```
/documentation/
  ├── PROJECT.md              # Main project documentation
  ├── QUICKSTART.md           # Quick start guide
  ├── TESTING.md              # Testing guide
  ├── IMPLEMENTATION_*.md     # Implementation details
  ├── *_SUMMARY.md            # Feature summaries
  ├── *_COMPLETE.md           # Completion reports
  └── requirements.txt        # Dependencies (if applicable)
```

### When Creating Documentation:
1. **Always check** if `/documentation` folder exists
2. **Place all new .md files** in `/documentation/`
3. **Use descriptive names** (e.g., `BIDIRECTIONAL_SYNC_COMPLETE.md`, `FREQUENCY_CONTROL_UPDATE.md`)
4. **Keep root clean** - avoid cluttering the project root with documentation files
5. **Update existing docs** in their current location (don't duplicate)

### Naming Conventions:
- Use UPPERCASE for significant documentation: `PROJECT.md`, `QUICKSTART.md`
- Use descriptive prefixes: `IMPLEMENTATION_`, `TESTING_`, `API_`
- Use suffixes for status: `_SUMMARY.md`, `_COMPLETE.md`, `_UPDATE.md`
- Be specific: `SLIDER_FIXES_SUMMARY.md` instead of `FIXES.md`

### Benefits:
✅ Keeps project root clean and organized
✅ Easy to find all documentation in one place
✅ Prevents documentation files from being scattered
✅ Makes it clear where new documentation should go
✅ Improves project maintainability

## Example Commands:
When creating documentation, use paths like:
- `c:\Projects\wave-flex-spots\documentation\FEATURE_NAME.md`
- NOT: `c:\Projects\wave-flex-spots\FEATURE_NAME.md`
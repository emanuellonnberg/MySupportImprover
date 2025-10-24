# Release Process Guide

This document describes how to create a new release of the My Support Improver plugin.

## Version Numbering

We follow [Semantic Versioning](https://semver.org/) (SemVer):

- **MAJOR.MINOR.PATCH** (e.g., 1.0.0)
  - **MAJOR**: Breaking changes that require user action
  - **MINOR**: New features, backwards compatible
  - **PATCH**: Bug fixes, backwards compatible

### Examples:
- `1.0.0` → `1.0.1` - Bug fix release
- `1.0.0` → `1.1.0` - New feature added
- `1.0.0` → `2.0.0` - Breaking changes (e.g., settings format changed)

## Pre-Release Checklist

Before creating a release, ensure:

- [ ] All changes are committed and pushed
- [ ] Tests pass (if applicable)
- [ ] Code is reviewed
- [ ] CHANGELOG.md is updated with new version section
- [ ] plugin.json version is updated to match
- [ ] README.md is up to date
- [ ] No known critical bugs

## Release Steps

### Method 1: Automated GitHub Release (Recommended)

This method automatically builds and publishes releases using GitHub Actions.

1. **Update version numbers:**
   ```bash
   # Edit plugin.json and update version
   # Edit CHANGELOG.md and add new version section
   ```

2. **Commit changes:**
   ```bash
   git add plugin.json CHANGELOG.md
   git commit -m "Bump version to X.Y.Z"
   git push
   ```

3. **Create and push a version tag:**
   ```bash
   git tag -a vX.Y.Z -m "Release version X.Y.Z"
   git push origin vX.Y.Z
   ```

4. **GitHub Actions will automatically:**
   - Verify version consistency
   - Build the package
   - Extract release notes from CHANGELOG.md
   - Create a GitHub Release
   - Attach the package zip file

5. **Verify the release:**
   - Go to: https://github.com/emanuellonnberg/MySupportImprover/releases
   - Check that the release was created
   - Download and test the package

### Method 2: Manual Release

If you need to create a release manually:

1. **Build the package:**

   **Linux/macOS:**
   ```bash
   ./package.sh
   ```

   **Windows:**
   ```batch
   package.bat
   ```

2. **Test the package:**
   - Extract the zip to a test Cura plugins folder
   - Launch Cura
   - Verify the plugin loads and works

3. **Create GitHub release:**
   - Go to: https://github.com/emanuellonnberg/MySupportImprover/releases/new
   - Create tag: `vX.Y.Z`
   - Release title: `Release vX.Y.Z`
   - Copy release notes from CHANGELOG.md
   - Attach the generated zip file
   - Publish release

## Post-Release Tasks

After creating a release:

- [ ] Test the release download and installation
- [ ] Announce on relevant forums/communities (if applicable)
- [ ] Monitor for bug reports
- [ ] Update any external documentation
- [ ] Consider submitting to Cura Marketplace (future)

## Hotfix Release Process

For urgent bug fixes:

1. Create a hotfix branch from the release tag
2. Fix the bug
3. Update version (increment PATCH number)
4. Update CHANGELOG.md
5. Follow normal release process
6. Merge hotfix back to main branch

## Rolling Back a Release

If a release has critical issues:

1. **Delete the release** on GitHub (if just published)
2. **Delete the tag:**
   ```bash
   git tag -d vX.Y.Z
   git push origin :refs/tags/vX.Y.Z
   ```
3. **Fix the issues**
4. **Create a new patch release**

## Version Verification

Before tagging, verify version consistency:

```bash
# Check plugin.json version
grep version plugin.json

# Check CHANGELOG.md has entry for new version
grep "\[X.Y.Z\]" CHANGELOG.md

# Verify presets.json version (should match)
grep version presets.json
```

## GitHub Actions Workflow

The automated release workflow (`.github/workflows/release.yml`):

- **Trigger**: Pushing a tag matching `v*.*.*`
- **Actions**:
  1. Checkout code
  2. Verify version consistency
  3. Build package
  4. Extract changelog notes
  5. Create GitHub release
  6. Upload artifact

**Required**: Repository must have GitHub Actions enabled.

## Troubleshooting

### Version mismatch error

If the GitHub Action fails with version mismatch:
- Ensure `plugin.json` version matches the git tag (without the 'v')
- Example: Tag `v1.0.0` requires `"version": "1.0.0"` in plugin.json

### Build fails

- Check all required files are committed
- Verify file paths in package scripts
- Test local build first

### Release not created

- Check GitHub Actions logs
- Verify `GITHUB_TOKEN` permissions
- Ensure tag was pushed to remote

## Release Checklist Summary

```
Version: ______

Pre-Release:
[ ] CHANGELOG.md updated
[ ] plugin.json version updated
[ ] README.md current
[ ] All changes committed
[ ] Tests pass

Release:
[ ] Version tag created: v______
[ ] Tag pushed to GitHub
[ ] GitHub Actions passed
[ ] Release created on GitHub
[ ] Package attached to release

Post-Release:
[ ] Download and test package
[ ] Verify in Cura
[ ] Monitor for issues
```

## Contact

For questions about the release process, open an issue on GitHub.

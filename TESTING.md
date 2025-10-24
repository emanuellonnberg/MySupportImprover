# Testing the Release Process

This guide helps you test the release infrastructure without creating an official release.

## Quick Start: Test Locally

The fastest way to test:

```bash
./package.sh
```

This creates `MySupportImprover-1.0.0.zip` which you can:
1. Extract and copy to your Cura plugins folder
2. Test in Cura to verify everything works
3. Delete when done testing

**No git operations, no releases, just a local build!**

---

## Option 1: Create a Beta Release (Recommended First Test)

Test the full automated release pipeline with a beta version:

```bash
# Create a beta tag (no need to change plugin.json!)
git tag -a v1.0.0-beta.1 -m "Beta test release"
git push origin v1.0.0-beta.1
```

**What happens:**
- GitHub Actions builds the package automatically
- Creates a release marked as "Pre-release"
- You can download and test from GitHub Releases
- Version validation is skipped (beta doesn't need to match plugin.json)

**To delete the beta test:**
```bash
# Delete from GitHub UI: Go to Releases → Delete the beta release
# Then delete the tag:
git tag -d v1.0.0-beta.1
git push origin :refs/tags/v1.0.0-beta.1
```

---

## Option 2: GitHub Test Build (No Release)

Trigger a test build without creating any release or tag:

1. **Push your branch to GitHub** (already done!)
2. **Go to GitHub:**
   - Navigate to: Actions → Test Build → Run workflow
   - Select your branch
   - Enter a version suffix (e.g., "test-initial")
   - Click "Run workflow"

3. **Wait for build** (takes ~1-2 minutes)

4. **Download artifact:**
   - Click on the completed workflow run
   - Scroll to "Artifacts" section
   - Download `MySupportImprover-1.0.0-test-initial`

5. **Test in Cura:**
   - Extract the zip
   - Copy to Cura plugins folder
   - Restart Cura

**Benefits:**
- No tags created
- No releases published
- Perfect for testing workflow itself
- Includes build metadata in README

---

## Option 3: Pull Request Test Build

When you create a PR, test builds are automatic:

```bash
# If you want to test via PR:
# (You'd do this from GitHub UI or:)
# gh pr create --title "Test release infrastructure" --body "Testing builds"
```

Builds are automatically created with version: `1.0.0-pr<number>-<sha>`

---

## Recommended Testing Order

### Phase 1: Local Test ✓ (DONE)
```bash
./package.sh  # Already tested successfully!
```

### Phase 2: GitHub Test Build (Next)
1. Go to GitHub Actions
2. Run "Test Build" workflow
3. Download and verify artifact

### Phase 3: Beta Release Test
```bash
git tag -a v1.0.0-beta.1 -m "Beta test"
git push origin v1.0.0-beta.1
```
Test the full release pipeline with pre-release.

### Phase 4: Stable Release (When Ready)
```bash
# Update CHANGELOG.md
# Ensure plugin.json is 1.0.0
git add CHANGELOG.md plugin.json
git commit -m "Prepare for 1.0.0 release"
git push

git tag -a v1.0.0 -m "Release version 1.0.0"
git push origin v1.0.0
```

---

## What We Built

✅ **Version Management**
- Semantic versioning (1.0.0)
- CHANGELOG.md with version history
- Versioned presets.json

✅ **Build Scripts**
- package.sh (Linux/macOS) - Tested successfully!
- package.bat (Windows)
- 15KB package size

✅ **GitHub Actions**
- Automated stable releases (v1.0.0)
- Pre-release support (v1.0.0-beta.1, etc.)
- Manual test builds (no tags/releases)
- PR test builds (automatic)

✅ **Documentation**
- README.md - User guide
- RELEASE.md - Release process guide
- CHANGELOG.md - Version history
- TESTING.md - This file!

---

## Next Steps

1. **Test the GitHub workflow:**
   - Go to Actions → Test Build → Run workflow

2. **Try a beta release:**
   - `git tag -a v1.0.0-beta.1 -m "Beta test"`
   - `git push origin v1.0.0-beta.1`

3. **When satisfied, create v1.0.0:**
   - Update CHANGELOG.md if needed
   - Tag and push v1.0.0

---

## Troubleshooting

### Build fails locally
- Make sure all files exist
- Check package.sh has execute permission: `chmod +x package.sh`

### GitHub Actions fails
- Check Actions tab for detailed logs
- Verify GitHub Actions is enabled in repo settings

### Version mismatch error (stable release only)
- Ensure plugin.json version matches tag (without 'v')
- Pre-releases skip this check

---

## Clean Up Test Builds

**Remove local build:**
```bash
rm MySupportImprover-*.zip
rm -rf build/
```

**Remove beta tag:**
```bash
git tag -d v1.0.0-beta.1
git push origin :refs/tags/v1.0.0-beta.1
```

**GitHub artifacts expire automatically after 30 days**

# Cura Marketplace Submission Guide

## Do I Need to Submit to the Marketplace?

**Short answer: No, not for testing or personal use!**

You can use your plugin indefinitely by manually installing it. The marketplace is only for public distribution.

## When to Consider Marketplace Submission

Submit to the Cura Marketplace if you want to:
- ✅ Share your plugin with the wider Cura community
- ✅ Allow easy one-click installation for users
- ✅ Get automatic updates for users
- ✅ Increase visibility and adoption

## Marketplace Submission Process

### Prerequisites

Before submitting, ensure:
- [ ] Plugin is thoroughly tested and stable
- [ ] All documentation is complete (README, etc.)
- [ ] Version is stable (e.g., 1.0.0, not beta)
- [ ] License is specified (you have LGPLv3 ✓)
- [ ] No known critical bugs

### Step 1: Create a Marketplace Package

The Cura Marketplace uses a different package format than our current release format.

**Required structure:**
```
package.json           # Marketplace metadata
plugin.json           # Your existing plugin metadata
MySupportImprover/    # Your plugin folder
```

**Create package.json:**
```json
{
    "package_id": "MySupportImprover",
    "package_type": "plugin",
    "display_name": "My Support Improver",
    "description": "Create customizable cutting volumes to control support generation settings in specific areas.",
    "package_version": "1.0.0",
    "sdk_version": 8,
    "author": {
        "author_id": "emanuellonnberg",
        "display_name": "Emanuel Lönnberg"
    },
    "website": "https://github.com/emanuellonnberg/MySupportImprover",
    "tags": [
        "support",
        "modifier",
        "volume",
        "cutting mesh"
    ],
    "icon_url": "https://raw.githubusercontent.com/emanuellonnberg/MySupportImprover/main/down.svg"
}
```

### Step 2: Submit to Ultimaker's Plugin Repository

**Repository:** https://github.com/Ultimaker/cura-plugins

**Process:**
1. **Fork** the repository
2. **Create** a new folder: `plugins/MySupportImprover/`
3. **Add** your plugin files with package.json
4. **Create** a Pull Request
5. **Wait** for Ultimaker team review

**What they review:**
- Code quality and security
- No malicious code
- Proper error handling
- Documentation quality
- User experience
- Compatibility with Cura versions

**Timeline:**
- Review can take several weeks to months
- They may request changes
- Not all plugins are accepted

### Step 3: Maintain Your Marketplace Listing

Once accepted:
- Update via pull requests to the same repository
- Increment version numbers properly
- Maintain backward compatibility when possible
- Respond to user issues

## Alternative: Self-Distribution

**You don't need the marketplace!** Many plugins are distributed via:

### GitHub Releases (What We Set Up!)
✅ You already have this!
- Users download from your Releases page
- You maintain full control
- Faster updates (no approval needed)
- Users follow your INSTALL.md guide

### Direct Distribution
- Share the zip file directly
- Email, Discord, forums, etc.
- Users install manually

### Your Own Website
- Host downloads on your site
- Provide installation instructions
- Full control over distribution

## Recommendation for Your Plugin

### Phase 1: Current (Beta Testing)
- ✅ Use GitHub Releases (already set up!)
- ✅ Share with friends/testers
- ✅ Gather feedback
- ✅ Fix issues

### Phase 2: Stable Release
- Release v1.0.0 on GitHub
- Continue using GitHub for distribution
- Build a user base
- Collect feedback and improve

### Phase 3: Consider Marketplace (Optional)
- After v1.0.0 is stable and well-tested
- If you want wider distribution
- If you're ready for community support requests
- If you want to contribute to the official ecosystem

## Marketplace Pros & Cons

### Pros:
- ✅ Easy discovery by users
- ✅ One-click installation
- ✅ Built into Cura
- ✅ Larger potential user base
- ✅ Community credibility

### Cons:
- ❌ Slow approval process
- ❌ Update delays (every update needs approval)
- ❌ Less control
- ❌ Strict requirements
- ❌ May require code changes

## Current Status: You're All Set!

**You already have everything you need:**
- ✅ GitHub repository
- ✅ Automated releases
- ✅ Professional documentation
- ✅ Easy installation process
- ✅ Version management

**Users can install your plugin right now by:**
1. Going to your GitHub Releases
2. Downloading the zip
3. Following INSTALL.md

## Resources

- **Cura Plugin Development:** https://github.com/Ultimaker/Cura/wiki/Plugin-Directory
- **Marketplace Plugins:** https://github.com/Ultimaker/cura-plugins
- **Cura API Documentation:** https://github.com/Ultimaker/Uranium (Uranium framework)
- **Example Plugins:** Browse the cura-plugins repo for examples

## Questions to Consider

Before submitting to marketplace, ask yourself:

1. **Is the plugin stable?** (Should be on v1.0.0+, thoroughly tested)
2. **Can I support users?** (Will you respond to issues and questions?)
3. **Is it beneficial to others?** (Not just for personal use)
4. **Can I maintain it long-term?** (Updates for new Cura versions)

If yes to all → Consider marketplace submission
If unsure → Stick with GitHub releases for now

---

## Bottom Line

**For testing and personal use:** Manual installation (INSTALL.md) is perfect!

**For sharing with a few people:** GitHub Releases works great!

**For wide public distribution:** Consider Marketplace (but it's optional!)

You can always start with GitHub and submit to the marketplace later when you're ready.

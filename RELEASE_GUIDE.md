# Release Guide - Marstek Cloud Battery Integration

## 🚀 Ready for Release!

Your integration is ready for release with proper attribution to the original developer [@DoctaShizzle](https://github.com/DoctaShizzle/marstek_cloud).

## 📋 Current Status

- **Branch**: `main` ✅
- **Latest Commit**: `7a7346f` (Attribution added)
- **Version Tags**: `v0.3.0`, `v0.3.1` ✅
- **HACS Ready**: ✅
- **Attribution Complete**: ✅

## 🔧 Commands to Run

### 1. Push to GitHub
```bash
# Push main branch
git push origin main

# Push all tags
git push origin --tags
```

### 2. Alternative: Push with Authentication
If you have GitHub CLI installed:
```bash
gh auth login
git push origin main
git push origin --tags
```

Or with personal access token:
```bash
git push https://YOUR_USERNAME:YOUR_TOKEN@github.com/d0n0van/marstek_cloud.git main
git push https://YOUR_USERNAME:YOUR_TOKEN@github.com/d0n0van/marstek_cloud.git --tags
```

## 📦 Create GitHub Release

### Option 1: Using GitHub CLI
```bash
gh release create v0.3.1 \
  --title "Marstek Cloud Battery v0.3.1 - HACS Ready with Attribution" \
  --notes "## 🎉 HACS-Ready Release with Proper Attribution

### ✨ New Features
- **HACS Support**: Easy installation via Home Assistant Community Store
- **Energy Dashboard Integration**: Native kWh sensors with proper state_class and device_class
- **API Optimizations**: Smart caching, adaptive intervals, and reduced API calls
- **Production Ready**: Comprehensive testing, error handling, and documentation

### 🔧 Technical Improvements
- Smart token management with automatic refresh
- 30-second response caching to reduce API calls
- Adaptive scan intervals (1-5 minutes based on data changes)
- Comprehensive unit and integration tests
- Type hints and code quality improvements

### 🙏 Attribution
This is a fork of the original work by [@DoctaShizzle](https://github.com/DoctaShizzle/marstek_cloud).
All original work and credits go to the original developer.

### 📋 Installation
1. Install via HACS (recommended)
2. Or download and extract to custom_components/
3. Restart Home Assistant
4. Add integration via Settings → Devices & Services

### 🔗 Links
- **Original Repository**: https://github.com/DoctaShizzle/marstek_cloud
- **Fork Repository**: https://github.com/d0n0van/marstek_cloud
- **HACS**: Search for 'Marstek Cloud Battery' in HACS" \
  --prerelease=false
```

### Option 2: Manual GitHub Release
1. Go to https://github.com/d0n0van/marstek_cloud/releases
2. Click **"Create a new release"**
3. **Tag version**: `v0.3.1`
4. **Release title**: `Marstek Cloud Battery v0.3.1 - HACS Ready with Attribution`
5. **Description**: Use the content from the GitHub CLI example above
6. **Attach files**: Upload `custom_components/marstek_cloud/` as a zip file
7. Click **"Publish release"**

## 🎯 HACS Submission

After the release is published:

1. **Join HACS Discord**: https://discord.gg/5a5J7UK
2. **Create Discussion**: "New Integration: Marstek Cloud Battery"
3. **Include**:
   - Repository URL: `https://github.com/d0n0van/marstek_cloud`
   - Brief description of features
   - Note that it's a fork with proper attribution

## 📊 Release Checklist

- [x] Code is on main branch
- [x] All tests passing
- [x] Proper attribution added
- [x] HACS structure ready
- [x] Version tags created
- [x] Documentation updated
- [ ] Push to GitHub (requires authentication)
- [ ] Create GitHub release
- [ ] Submit to HACS

## 🔗 Quick Links

- **Repository**: https://github.com/d0n0van/marstek_cloud
- **Original**: https://github.com/DoctaShizzle/marstek_cloud
- **HACS Discord**: https://discord.gg/5a5J7UK
- **Home Assistant Community**: https://community.home-assistant.io/

## 🎉 Success!

Once released, users will be able to:
1. Install via HACS easily
2. Use native Energy Dashboard integration
3. Benefit from optimized API calls
4. Enjoy production-ready reliability

Your integration is ready to help the Home Assistant community! 🚀

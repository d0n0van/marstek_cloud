# HACS Submission Guide

## ✅ Your Integration is Ready for HACS!

Your Marstek Cloud Battery integration has been properly structured for HACS submission and is now on the main branch with proper version tagging.

> **📝 Attribution**: This is a fork of the original [Marstek Cloud integration](https://github.com/DoctaShizzle/marstek_cloud) by [@DoctaShizzle](https://github.com/DoctaShizzle). All original work and credits go to the original developer.

## 📁 Repository Structure

```
marstek_cloud/
├── custom_components/
│   ├── hacs.json
│   └── marstek_cloud/
│       ├── __init__.py
│       ├── config_flow.py
│       ├── const.py
│       ├── coordinator.py
│       ├── manifest.json
│       └── sensor.py
├── hacs.json
├── README.md
└── ... (other files)
```

## 🔧 HACS Configuration

### hacs.json (Root)
```json
{
  "name": "Marstek Cloud Battery",
  "content_in_root": false,
  "domains": ["sensor"],
  "homeassistant": "2024.1.0",
  "iot_class": "cloud_polling"
}
```

### manifest.json
```json
{
  "domain": "marstek_cloud",
  "name": "Marstek Cloud Battery",
  "version": "0.3.0",
  "documentation": "https://github.com/d0n0van/marstek_cloud",
  "issue_tracker": "https://github.com/d0n0van/marstek_cloud/issues",
  "requirements": ["aiohttp>=3.8.0", "voluptuous>=0.12.0"],
  "codeowners": ["@d0n0van"],
  "iot_class": "cloud_polling",
  "config_flow": true
}
```

## 🚀 How to Submit to HACS

### Step 1: Push to GitHub
```bash
# Changes are already on main branch
git push origin main
git push origin v0.3.0  # Push the version tag
```

### Step 2: Create a Release
1. Go to your GitHub repository: https://github.com/d0n0van/marstek_cloud
2. Click **Releases** → **Create a new release**
3. Tag version: `v0.3.0`
4. Release title: `Marstek Cloud Battery v0.3.0`
5. Description: Include the changelog and features
6. Upload the `custom_components/marstek_cloud/` folder as a zip file

### Step 3: Submit to HACS
1. Go to the [HACS Discord](https://discord.gg/5a5J7UK) or [GitHub Discussions](https://github.com/hacs/integration/discussions)
2. Create a new discussion with:
   - **Title**: "New Integration: Marstek Cloud Battery"
   - **Category**: "New Integration"
   - **Content**: Include repository URL and brief description

### Step 4: HACS Review Process
- HACS maintainers will review your integration
- They'll check for proper structure, manifest, and functionality
- Once approved, it will be available in HACS!

## 📋 HACS Requirements Checklist

- ✅ **Repository Structure**: `custom_components/marstek_cloud/` directory
- ✅ **manifest.json**: Proper domain, version, requirements, codeowners
- ✅ **hacs.json**: Configuration file present
- ✅ **README.md**: Clear installation and usage instructions
- ✅ **Code Quality**: Well-structured, documented code
- ✅ **Home Assistant Compatibility**: Works with HA 2024.1.0+
- ✅ **Config Flow**: User-friendly setup process
- ✅ **Error Handling**: Proper exception handling
- ✅ **Logging**: Appropriate logging levels

## 🎯 Next Steps

1. **Push your changes** to GitHub
2. **Create a release** with proper versioning
3. **Submit to HACS** via Discord or GitHub Discussions
4. **Wait for approval** (usually 1-3 days)
5. **Celebrate** when users can install your integration via HACS! 🎉

## 📞 Support

- **GitHub Issues**: https://github.com/d0n0van/marstek_cloud/issues
- **HACS Discord**: https://discord.gg/5a5J7UK
- **Home Assistant Community**: https://community.home-assistant.io/

Your integration is production-ready and follows all HACS best practices! 🚀

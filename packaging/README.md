# Packaging

```bash
python -m pip install -r requirements-gui.txt pyinstaller
pyinstaller packaging/pokerlab.spec --noconfirm
```

Result: `dist/PokerLab/` on any platform and `dist/PokerLab.app` on macOS. The
app opens Vision Studio; `PokerLab --lab` opens the Agent Lab directly.

Status: the recipe was built and started headless on Linux
(`PokerLab --lab --screenshot out.png`). The macOS bundle has not been built or
opened on a Mac yet; `.github/workflows/mac-app.yml` does that on demand and
uploads the result. Treat the first run as a test.

## Signing and notarizing (needs your Apple Developer ID)

An unsigned or ad-hoc-signed app is blocked by Gatekeeper on other people's
Macs. With a Developer ID Application certificate in your keychain:

```bash
codesign --force --deep --options runtime --timestamp \
  --sign "Developer ID Application: YOUR NAME (TEAMID)" dist/PokerLab.app
ditto -c -k --keepParent dist/PokerLab.app PokerLab.zip
xcrun notarytool submit PokerLab.zip --apple-id YOU@EXAMPLE.COM --team-id TEAMID --wait
xcrun stapler staple dist/PokerLab.app
```

Screen Recording permission is requested by Vision Studio only; the Agent Lab
needs no permissions.

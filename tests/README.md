# Installer regression test

This small regression test exercises the existing Windows pack installer without changing its behaviour or the Packs structure.

It copies `Install Packs.bat` and one known-good `variation` fixture into a temporary directory, runs the installer with its existing `PB_INSTALL_ALL=1` non-interactive mode, and verifies that the JSON is moved unchanged to `packs/controls/`.

Run on Windows from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tests/installer-valid-pack.ps1
```

The test uses only a temporary directory and removes it when finished.

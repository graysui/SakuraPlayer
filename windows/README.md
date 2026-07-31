# SakuraPlayer Windows

Private Windows 10/11 desktop client built with Flutter 3.29.2 and Dart 3.7.2.

This project intentionally contains only the Windows platform runner.

## Verification and private release

Run the default offline client and AC-129 algorithm checks from the repository
root:

```powershell
windows\tool\run_default_tests.ps1
```

Build the release directory, verify native libraries and licenses, and create
the private ZIP installer:

```powershell
windows\tool\build_private_release.ps1
```

The package includes per-user install/uninstall scripts and SHA-256 manifests.
Pass `-CertificateThumbprint` only when an approved code-signing certificate is
available in the current user's certificate store. No public store metadata is
generated.

`tool\run_real115_probe.ps1` is excluded from every default command. It requires
the explicit marker and local acceptance environment described by the runtime
configuration contract. TASK-213 owns execution and final AC-130 evidence.

## Getting Started

This project is a starting point for a Flutter application.

A few resources to get you started if this is your first Flutter project:

- [Lab: Write your first Flutter app](https://docs.flutter.dev/get-started/codelab)
- [Cookbook: Useful Flutter samples](https://docs.flutter.dev/cookbook)

For help getting started with Flutter development, view the
[online documentation](https://docs.flutter.dev/), which offers tutorials,
samples, guidance on mobile development, and a full API reference.

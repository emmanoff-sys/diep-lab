# Build Framework — DAEP / RE-OS

## Authority
- LLD v2.0 §2.1.2 (`pyproject.toml` as the build-system configuration file for every service and library)
- HLD Technology Stack volume (Python / FastAPI, React / Next.js, Flutter as the DAEP / RE-OS runtimes)
- WP-001-09 Engineering Package

---

## Quick Reference

| Runtime | Prereq Command | Build Command | Output Location |
|---------|---------------|---------------|-----------------|
| Python (wheel) | `pip install build` | `python -m build --wheel` | `dist/*.whl` |
| Python (sdist) | `pip install build` | `python -m build --sdist` | `dist/*.tar.gz` |
| Python (both) | `pip install build` | `python -m build` | `dist/` |
| React / Next.js | `npm ci` | `npm run build` | `.next/` |
| Flutter (Android APK) | `flutter pub get` | `flutter build apk --release` | `build/app/outputs/flutter-apk/app-release.apk` |
| Flutter (iOS) | `flutter pub get` | `flutter build ios --release` | `build/ios/iphoneos/Runner.app` |
| Flutter (Web) | `flutter pub get` | `flutter build web --release` | `build/web/` |

---

## 1. Python Services and Libraries

All Python services and shared libraries use **hatchling** as the PEP 621 build backend, declared in `[build-system]` of each service's `pyproject.toml`. Build output is a Python wheel (`.whl`) suitable for publication to the internal artifact repository (WP-001-11) and for consumption as a versioned dependency by other services.

### 1.1 Build System Configuration

Every Python service/library `pyproject.toml` declares:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/<service_name>"]
```

This is the single build-backend choice for all Python components in DAEP / RE-OS. Do not use setuptools, poetry, or flit in new services — diverging backends fragment the build pipeline and break the reproducibility guarantee from WP-001-08.

### 1.2 Prerequisites

```bash
pip install build hatchling
```

### 1.3 Build Commands

```bash
# Navigate to the service or library root (directory containing pyproject.toml).
cd templates/python-service   # or services/your-service, libs/your-library

# Build a wheel (primary output for distribution and internal publish).
python -m build --wheel

# Build a source distribution.
python -m build --sdist

# Build both wheel and sdist.
python -m build
```

Output appears in `dist/`:
```
dist/
  service_name-0.1.0-py3-none-any.whl
  service_name-0.1.0.tar.gz
```

### 1.4 Build Verification

After building, verify the wheel is well-formed:

```bash
# Inspect wheel contents.
python -m zipfile -l dist/*.whl

# Install into a fresh virtualenv and verify import.
python -m venv /tmp/build-verify
source /tmp/build-verify/bin/activate
pip install dist/*.whl
python -c "import service_name; print('Build OK')"
deactivate
rm -rf /tmp/build-verify
```

### 1.5 Before Building a New Service from the Scaffold

Rename `service_name` to the actual service identifier throughout:

1. `pyproject.toml [project].name` (e.g., `"device-registry"`)
2. `[tool.hatch.build.targets.wheel].packages` (e.g., `["src/device_registry"]`)
3. `src/service_name/` directory → `src/device_registry/`
4. All `from service_name.` imports → `from device_registry.`

Full renaming steps are in `templates/python-service/README.md`.

---

## 2. React / Next.js Application

The React / Next.js web application lives under `apps/web/` (directory TBD — will be confirmed when EPIC-002 defines the `apps/` structure per HLD).

### 2.1 Prerequisites

Node.js 20 LTS or later.

```bash
# Install exact dependency tree from package-lock.json.
# Always use 'npm ci', not 'npm install', to enforce the lock file.
npm ci
```

### 2.2 Build Commands

```bash
# Navigate to the Next.js app root.
cd apps/web

# Production build.
npm run build

# Preview the production build locally.
npm run start
```

### 2.3 Build Output

`npm run build` produces `.next/` containing static bundles, server-side rendering modules, and optimisation manifests. This output is consumed by the Docker image build in EPIC-003 / WP-003-01.

---

## 3. Flutter Application

The Flutter mobile and web application lives under `apps/mobile/` (directory TBD — will be confirmed when EPIC-002 defines the `apps/` structure per HLD).

### 3.1 Prerequisites

Flutter SDK 3.x or later.

```bash
# Fetch exact dependency tree from pubspec.lock.
flutter pub get
```

### 3.2 Build Commands

```bash
# Navigate to the Flutter app root.
cd apps/mobile

# Android APK — release mode.
flutter build apk --release

# iOS archive — requires macOS with Xcode installed.
flutter build ios --release

# Web application.
flutter build web --release
```

### 3.3 Build Output

| Target | Output Path |
|--------|-------------|
| Android APK | `build/app/outputs/flutter-apk/app-release.apk` |
| iOS | `build/ios/iphoneos/Runner.app` |
| Web | `build/web/` |

---

## 4. Build Reproducibility Requirement

Builds from the same source at the same commit must produce byte-identical output regardless of the build environment (developer workstation, CI runner, production VM). This is enforced by:

| Runtime | Mechanism |
|---------|-----------|
| Python | Exact-pinned `requirements.txt` (WP-001-08); hatchling backend; Python 3.11 |
| JavaScript | `package-lock.json` committed and enforced via `npm ci` |
| Flutter | `pubspec.lock` committed and enforced via `flutter pub get` |

If a build produces different output between environments, **stop** — investigate the root cause before merging. The most common causes are: an un-committed lock file, a floating `>=` version in a dependency config, or a Python version mismatch (must be 3.11 per LLD v2.0 §2.1).

---

## 5. CI Integration

This build framework is invoked in CI by EPIC-004:

| CI Stage | WP | Command |
|----------|----|---------|
| Stage 4 — Python build | WP-004-04 | `python -m build --wheel` |
| Stage 5 — Next.js build | WP-004-05 | `npm run build` |
| Stage 5 — Flutter build | WP-004-05 | `flutter build apk --release` |
| Stage 7 — Push to registry | WP-004-06 | Docker build consuming wheel output |

---

## 6. Traceability

| Artefact | Reference |
|----------|-----------|
| LLD v2.0 §2.1.2 | `pyproject.toml` as build-system configuration |
| HLD Technology Stack | Python / FastAPI, React / Next.js, Flutter runtimes |
| WP-001-08 | Dependency Policy (exact-pin — feeds build reproducibility) |
| WP-001-09 | This document |
| WP-001-11 | Artifact Repository (publish destination for Python wheels) |
| WP-003-01 | Docker image build (consumes Python wheel and frontend build output) |
| WP-004-04 | CI Python lint and test pipeline (invokes `python -m build`) |

"""One fixed Android test candidate. No publishing entrypoint or release token."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import re
import shutil
import sys
import urllib.request

import pipeline as p

SHA = "601d6b4d811da18f8b437febe6f677df5cfa4da2"
SOURCE_REF = "refs/heads/codex/offline-browsing-and-playback-20261017"
PARENT = "b19087a0fc8d2a27b35d8151c5a59fa791c8c4db"
MESSAGE = "build: retry offline candidate 601d6b4 with explicit SDK tools"
REQUEST_PATH = "requests/offline-601d6b4.json"
SOURCE_VERSION = "1.0.6+23"
VERSION_NAME = "1.0.6-offline.601d6b4"
VERSION_CODE = 23
PACKAGE_VERSION = VERSION_NAME + "+" + str(VERSION_CODE)
APK_NAME = "emosonic_android_offline_601d6b4_v" + PACKAGE_VERSION + ".apk"
BASELINE_URL = "https://github.com/jsdfhasuh/emosonic-releases/releases/download/v1.0.6%2B23/emosonic_android_v1.0.6%2B23.apk"
REQUEST = {"source_sha": SHA, "source_version": SOURCE_VERSION,
           "version_name": VERSION_NAME, "version_code": VERSION_CODE, "mode": "build-only", "attempt": 2}


def context():
    p.require(p.POLICY["source_repository"] == p.SOURCE and p.POLICY["release_repository"] == p.DEST
              and p.POLICY["builder_repository"] == p.BUILDER, "Repository policy mismatch.")
    p.require(p.POLICY["source_ref"] == p.SOURCE_REF, "Stable source policy changed.")
    p.require(os.environ.get("GITHUB_REPOSITORY") == p.BUILDER, "Untrusted builder repository.")
    p.require(os.environ.get("GITHUB_REF") == "refs/heads/main", "Only trusted main may run.")
    p.require(os.environ.get("GITHUB_EVENT_NAME") == "push", "Only the fixed candidate push may run.")
    p.require(os.environ.get("GITHUB_WORKFLOW_REF") == p.BUILDER + "/.github/workflows/offline-candidate.yml@refs/heads/main", "Unexpected candidate workflow.")
    builder_sha = p.checked_sha(os.environ.get("GITHUB_SHA"))
    for name in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
        p.require(re.fullmatch(r"[1-9][0-9]*", os.environ.get(name, "")), "Invalid workflow run identity.")
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    p.require(event.get("before") == PARENT and event.get("after") == builder_sha
              and event.get("ref") == "refs/heads/main" and event.get("forced") is False
              and event.get("deleted") is False and event.get("created") is False,
              "Push is not the one authorized candidate transition.")
    head = event.get("head_commit") or {}
    p.require(head.get("id") == builder_sha and head.get("message") == MESSAGE,
              "Candidate push marker mismatch.")
    request = p.ROOT / REQUEST_PATH
    p.require(request.is_file() and not request.is_symlink()
              and json.loads(request.read_text(encoding="utf-8")) == REQUEST,
              "Candidate request is not the fixed reviewed request.")
    for name, value in (("SOURCE_SHA", SHA), ("BUILD_VERSION", SOURCE_VERSION)):
        p.require(os.environ.get(name) == value, "Candidate source or version override rejected.")
    p.require(not os.environ.get("RELEASE_WRITE_TOKEN") and not os.environ.get("RELEASE_MODE"),
              "Release credentials and release modes are forbidden in the test workflow.")


def tools():
    """Use installed inspection tools; sdkmanager is not necessarily on PATH."""
    sdk = Path(os.environ["ANDROID_HOME"])
    build_tools = sdk / "build-tools" / p.POLICY["android_build_tools"]
    if not all((build_tools / name).is_file() for name in ("aapt", "apksigner")):
        manager = sdk / "cmdline-tools/latest/bin/sdkmanager"
        p.require(manager.is_file(), "Android SDK command-line tools are missing from the runner.")
        p.quiet([str(manager), "build-tools;" + p.POLICY["android_build_tools"]])
    p.require(all((build_tools / name).is_file() for name in ("aapt", "apksigner")),
              "Pinned Android inspection tools are missing after setup.")
    print("Pinned Android inspection tools are available.")


def baseline():
    """Inspect the previously published binary before granting build Secrets."""
    path = p.ROOT / "baseline.apk"
    try:
        with urllib.request.urlopen(BASELINE_URL, timeout=180) as response, path.open("wb") as output:
            shutil.copyfileobj(response, output)
        p.require(p.file_digest(path) == p.POLICY["baseline_apk_sha256"], "Baseline APK digest mismatch.")
        p.inspect_apk(path, SOURCE_VERSION)
        print("Existing release APK verified: versionCode 23, versionName 1.0.6, original package and certificate.")
    finally:
        path.unlink(missing_ok=True)


def fetch():
    p.require_secrets(["SOURCE_READ_TOKEN"])
    p.require(p.remote_source_version(SHA, os.environ["SOURCE_READ_TOKEN"]) == SOURCE_VERSION,
              "Fixed source pubspec version mismatch.")
    p.fetch()


def metadata(digest):
    p.require(re.fullmatch(r"[0-9a-f]{64}", digest), "Invalid package digest.")
    return {"schema": "offline-test-1", "mode": "build-only", "prerelease": True,
            "published": False, "source_repository": p.SOURCE, "source_ref": SOURCE_REF,
            "source_sha": SHA, "source_version": SOURCE_VERSION,
            "version_name": VERSION_NAME, "version_code": VERSION_CODE,
            "builder_repository": p.BUILDER, "builder_sha": os.environ["GITHUB_SHA"],
            "run_id": os.environ["GITHUB_RUN_ID"], "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
            "application_id": p.POLICY["application_id"], "certificate_sha256": p.POLICY["certificate_sha256"],
            "abis": p.POLICY["abis"], "package_sha256": digest,
            "installation": "manual replacement; back up data; safe downgrade is not guaranteed"}


def bundle(directory):
    p.require(directory.is_dir() and not directory.is_symlink(), "Artifact directory missing.")
    expected = {APK_NAME, APK_NAME + ".sha256", "android-test-manifest.json"}
    p.require({path.name for path in directory.iterdir()} == expected, "Unexpected or missing test artifact files.")
    p.require(all(path.is_file() and not path.is_symlink() for path in directory.iterdir()), "Artifact links or directories rejected.")
    apk = directory / APK_NAME
    p.require(0 < apk.stat().st_size < 512 * 1024 * 1024, "APK size outside allowed range.")
    manifest = directory / "android-test-manifest.json"
    checksum = directory / (APK_NAME + ".sha256")
    p.require(manifest.stat().st_size < 8192 and checksum.stat().st_size < 256, "Oversized metadata rejected.")
    digest = p.file_digest(apk)
    p.require(checksum.read_text(encoding="ascii") == digest + "  " + APK_NAME + "\n", "Test APK checksum mismatch.")
    p.require(json.loads(manifest.read_text(encoding="utf-8")) == metadata(digest), "Test artifact provenance mismatch.")
    return digest


def stage(apk):
    dist = p.ROOT / "dist"
    dist.mkdir(mode=0o700)
    destination = dist / APK_NAME
    shutil.copyfile(apk, destination)
    digest = p.file_digest(destination)
    (dist / (APK_NAME + ".sha256")).write_text(digest + "  " + APK_NAME + "\n", encoding="ascii")
    (dist / "android-test-manifest.json").write_text(json.dumps(metadata(digest), indent=2) + "\n", encoding="utf-8")
    bundle(dist)


def build():
    p.require_secrets(["ANDROID_KEYSTORE_BASE64", "ANDROID_STORE_PASSWORD", "ANDROID_KEY_PASSWORD", "ANDROID_KEY_ALIAS"])
    source, source_version, sha, server = p.source_context()
    p.require(source_version == SOURCE_VERSION and sha == SHA, "Source context does not match the candidate.")
    keyfile = source / "android/key.properties"
    keystore = source / "android/keystore/emosonic-release.jks"
    defines = source / "build-defines.json"
    p.require(not keyfile.exists() and not keystore.exists() and not defines.exists(), "Unexpected signing or define file in source.")
    clean_env = p.build_env()
    try:
        p.codegen(source, clean_env)
        keystore.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        keystore.write_bytes(base64.b64decode(os.environ["ANDROID_KEYSTORE_BASE64"], validate=True))
        keystore.chmod(0o600)
        keyfile.write_text("storeFile=keystore/emosonic-release.jks\n" + "\n".join(
            key + "=" + p.property_escape(os.environ[secret]) for key, secret in [
                ("storePassword", "ANDROID_STORE_PASSWORD"), ("keyPassword", "ANDROID_KEY_PASSWORD"),
                ("keyAlias", "ANDROID_KEY_ALIAS")]) + "\n", encoding="ascii")
        keyfile.chmod(0o600)
        defines.write_text(json.dumps({"DEFAULT_SERVER_URL": server, "APP_UPDATE_SOURCE": "github", "GITHUB_RELEASE_REPOSITORY": p.DEST}), encoding="utf-8")
        defines.chmod(0o600)
        print("Fixed offline candidate APK build started (output suppressed).", flush=True)
        p.quiet(["flutter", "build", "apk", "--release", "--target-platform=android-arm,android-arm64,android-x64",
                 "--build-name=" + VERSION_NAME, "--build-number=" + str(VERSION_CODE),
                 "--dart-define-from-file=" + str(defines)], source, clean_env)
        apk = source / "build/app/outputs/flutter-apk/app-release.apk"
        p.inspect_apk(apk, PACKAGE_VERSION)
        stage(apk)
    finally:
        for path in (keyfile, keystore, defines):
            path.unlink(missing_ok=True)


def verify():
    directory = p.ROOT / "incoming"
    digest = bundle(directory)
    p.inspect_apk(directory / APK_NAME, PACKAGE_VERSION)
    print("Independent test APK checks passed: original signature/package, offline version, three ABIs and exact source provenance.")
    print("APK SHA-256: " + digest)


def main():
    try:
        context()
        stages = {"tools": tools, "baseline": baseline, "fetch": fetch, "build": build, "verify": verify, "cleanup": p.cleanup}
        p.require(len(sys.argv) == 2 and sys.argv[1] in stages, "Invalid candidate stage; publishing is unavailable.")
        stages[sys.argv[1]]()
    except p.GateError as error:
        print("ERROR: " + str(error), file=sys.stderr)
        return 1
    except Exception:
        print("ERROR: Candidate stage failed; sensitive details suppressed. Diagnose privately.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

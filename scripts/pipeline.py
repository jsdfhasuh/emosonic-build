"""Restricted Android + Windows builder. Never print subprocess/API bodies."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import struct
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "policy.json").read_text(encoding="utf-8"))
SOURCE = "jsdfhasuh/emosonic"
SOURCE_REF = "refs/heads/master"
DEST = "jsdfhasuh/emosonic-releases"
BUILDER = "jsdfhasuh/emosonic-build"
VERSION_RE = re.compile(r"(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})\+([1-9][0-9]{0,9})", re.ASCII)
SHA_RE = re.compile(r"[0-9a-f]{40}", re.ASCII)
NATIVE_CONTRACT_TEST_COUNT = 104
STABLE_PUSH_PARENT = "8b015c2cf4c86397acbe2491569fcb4b999f103b"
STABLE_PUSH_MESSAGE = "release: publish fixed native ACK and log sharing 1.0.9+26"
STABLE_PUSH_PATH = "requests/stable-1.0.9-26.json"
STABLE_PUSH_REQUEST = {"source_sha": "ecd827ec605577c31f3abcc3390fd53baf22df4c",
                       "version": "1.0.9+26", "mode": "publish-stable", "attempt": 1}



class GateError(Exception):
    """Only fixed, non-sensitive messages may be passed to this exception."""


def require(condition, message):
    if not condition:
        raise GateError(message)


def version(value):
    require(isinstance(value, str) and VERSION_RE.fullmatch(value), "Invalid version: expected X.Y.Z+BUILD.")
    parts = tuple(map(int, VERSION_RE.fullmatch(value).groups()))
    require(all(part <= 65535 for part in parts), "Version exceeds Windows 16-bit resource component limit.")
    return parts


def ref_input(value):
    require(value == SOURCE_REF, "Only refs/heads/master is allowed as the source branch.")
    return value


def checked_sha(value):
    require(isinstance(value, str) and SHA_RE.fullmatch(value), "Invalid source SHA.")
    return value


def release_version(tag):
    require(isinstance(tag, str), "Invalid release tag.")
    for prefix in ("android-v", "v"):
        if tag.startswith(prefix):
            return version(tag[len(prefix):])
    raise GateError("Unknown release tag format; manual review required.")


def monotonic(candidate, tags):
    current = version(candidate)
    floors = [release_version(POLICY["baseline_release"])]
    floors += [release_version(tag) for tag in tags]
    for old in floors:
        require(current[:3] >= old[:3] and current[3] > old[3], "Source version conflicts with release history. Update pubspec.yaml on master: version must not decrease and build number must increase.")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise GateError("Unexpected GitHub API redirect.")


def api(path, token=None, method="GET", data=None, upload=False):
    host = "https://uploads.github.com" if upload else "https://api.github.com"
    require(path.startswith("/repos/"), "Unexpected API path.")
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "emosonic-build"}
    if token:
        headers["Authorization"] = "Bearer " + token
    body = data
    if isinstance(data, dict):
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    elif data is not None:
        headers["Content-Type"] = "application/octet-stream"
    request = urllib.request.Request(host + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=180) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404 and method == "GET":
            return None
        raise GateError("GitHub API request failed; check permissions or release conflict.") from None
    except (urllib.error.URLError, TimeoutError):
        raise GateError("GitHub network request failed.") from None


def history(token=None, exclude_id=None, exclude_tag=None):
    tags = set()
    for collection in ("releases", "tags"):
        for page in range(1, 101):
            items = api(f"/repos/{DEST}/{collection}?per_page=100&page={page}", token)
            require(isinstance(items, list), "Unable to list destination history.")
            for item in items:
                if collection == "releases" and item.get("id") == exclude_id:
                    continue
                if collection == "tags" and item.get("name") == exclude_tag:
                    continue
                tags.add(item["tag_name"] if collection == "releases" else item["name"])
            if len(items) < 100:
                break
        else:
            raise GateError("Destination history exceeded safe pagination limit.")
    return tags


def output(name, value):
    require(name in {"source_sha", "version", "apk_name", "installer_name", "apk_sha256", "installer_sha256"} and "\n" not in value and "\r" not in value, "Unsafe workflow output.")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def require_secrets(names):
    for name in names:
        require(bool(os.environ.get(name)), "Required credential is missing; configure the documented Secrets.")


def context():
    require(POLICY["source_repository"] == SOURCE and POLICY["release_repository"] == DEST and POLICY["builder_repository"] == BUILDER, "Repository policy mismatch.")
    require(POLICY["source_ref"] == SOURCE_REF, "Source branch policy mismatch.")
    require(os.environ.get("GITHUB_REPOSITORY") == BUILDER, "Untrusted builder repository.")
    require(os.environ.get("GITHUB_REF") == "refs/heads/main", "Only trusted main may run.")
    if os.environ.get("GITHUB_EVENT_NAME") == "push":
        stable_push_context()
    else:
        require(os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch", "Only manual or the fixed stable request may run.")
    require(SHA_RE.fullmatch(os.environ.get("GITHUB_SHA", "")), "Invalid builder SHA.")
    require(re.fullmatch(r"[1-9][0-9]*", os.environ.get("GITHUB_RUN_ID", "")), "Invalid workflow run ID.")
    require(re.fullmatch(r"[1-9][0-9]*", os.environ.get("GITHUB_RUN_ATTEMPT", "")), "Invalid workflow attempt.")


def stable_push_context():
    require(os.environ.get("GITHUB_WORKFLOW_REF") == BUILDER + "/.github/workflows/android.yml@refs/heads/main", "Unexpected stable request workflow.")
    builder_sha = checked_sha(os.environ.get("GITHUB_SHA"))
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    require(event.get("before") == STABLE_PUSH_PARENT and event.get("after") == builder_sha
            and event.get("ref") == "refs/heads/main" and event.get("forced") is False
            and event.get("deleted") is False and event.get("created") is False,
            "Push is not the authorized stable transition.")
    head = event.get("head_commit") or {}
    require(head.get("id") == builder_sha and head.get("message") == STABLE_PUSH_MESSAGE,
            "Stable request push marker mismatch.")
    request = ROOT / STABLE_PUSH_PATH
    require(request.is_file() and not request.is_symlink()
            and json.loads(request.read_text(encoding="utf-8")) == STABLE_PUSH_REQUEST,
            "Stable request is not the fixed reviewed request.")
    for name, expected in (("SOURCE_SHA", STABLE_PUSH_REQUEST["source_sha"]),
                           ("BUILD_VERSION", STABLE_PUSH_REQUEST["version"]),
                           ("RELEASE_MODE", STABLE_PUSH_REQUEST["mode"])):
        require(name not in os.environ or os.environ[name] == expected,
                "Stable request source, version or mode override rejected.")


def source_version(pubspec):
    # Deliberately accept the original batch entrypoint's canonical plain scalar
    # format, not YAML aliases, merges, duplicate keys or multiple documents.
    require(isinstance(pubspec, str) and len(pubspec) <= 262144, "Invalid pubspec size or encoding.")
    require(not re.search(r"(?m)^(?:---|\.\.\.|%|<<[ \t]*:)", pubspec), "Unsupported pubspec document or merge syntax.")
    keys = re.findall(r"(?m)^(?:version|'version'|\"version\")[ \t]*:[^\r\n]*", pubspec)
    require(len(keys) == 1, "pubspec.yaml must contain exactly one plain top-level version: X.Y.Z+BUILD.")
    match = re.fullmatch(r"version:[ \t]*([^\s]+)[ \t]*", keys[0])
    require(match is not None, "Use a plain unquoted version: X.Y.Z+BUILD in pubspec.yaml, without inline comments.")
    candidate = match[1]
    version(candidate)
    return candidate


def remote_source_version(sha, token):
    checked_sha(sha)
    result = api(f"/repos/{SOURCE}/contents/pubspec.yaml?ref={sha}", token)
    require(isinstance(result, dict) and result.get("type") == "file" and result.get("path") == "pubspec.yaml" and result.get("encoding") == "base64", "Source pubspec.yaml is unavailable or not a regular file.")
    size = result.get("size")
    require(isinstance(size, int) and 0 < size <= 262144, "Invalid source pubspec size.")
    encoded = result.get("content")
    require(isinstance(encoded, str) and len(encoded) <= 360000, "Invalid source pubspec content.")
    try:
        data = base64.b64decode("".join(encoded.split()), validate=True)
        pubspec = data.decode("utf-8")
    except (ValueError, UnicodeError):
        raise GateError("Invalid source pubspec encoding.") from None
    require(len(data) == size and hashlib.sha1(b"blob " + str(size).encode() + b"\0" + data).hexdigest() == result.get("sha"), "Source pubspec integrity mismatch.")
    return source_version(pubspec)


def prepare():
    require_secrets(["SOURCE_READ_TOKEN"])
    require("BUILD_VERSION" not in os.environ, "Manual version overrides are disabled; update source pubspec.yaml.")
    require(os.environ.get("RELEASE_MODE") in ("build-only", "publish-stable"), "Invalid release mode.")
    ref = ref_input(os.environ.get("SOURCE_REF", SOURCE_REF))
    token = os.environ["SOURCE_READ_TOKEN"]
    result = api(f"/repos/{SOURCE}/git/ref/heads/master", token)
    require(isinstance(result, dict) and result.get("ref") == ref and isinstance(result.get("object"), dict) and result["object"].get("type") == "commit", "Source master branch could not be resolved to a commit.")
    sha = checked_sha(result["object"].get("sha"))
    candidate = remote_source_version(sha, token)
    if os.environ.get("GITHUB_EVENT_NAME") == "push":
        require(sha == STABLE_PUSH_REQUEST["source_sha"] and candidate == STABLE_PUSH_REQUEST["version"],
                "Master differs from the authorized stable source snapshot.")
    monotonic(candidate, history(os.environ.get("GITHUB_TOKEN")))
    output("source_sha", sha)
    output("version", candidate)
    output("apk_name", f"emosonic_android_v{candidate}.apk")
    output("installer_name", installer_name(candidate))
    print("Master resolved once to exact SHA; source pubspec version passed release-history gates.")


def quiet(args, cwd=None, env=None):
    # Compiler stderr can contain private source snippets, paths and secrets.
    # No retained log and no traceback containing argv, stderr or API response.
    try:
        result = subprocess.run(args, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    except OSError:
        raise GateError("Required tool is unavailable.") from None
    if result.returncode != 0:
        # Emit only fixed classifications and an integer, never excerpts or paths.
        raw = (result.stdout + result.stderr).decode("utf-8", errors="replace").lower()
        categories = [("not recognized as an internal or external command", "command-resolution"),
                      ("the system cannot find the path specified", "missing-launcher-path"),
                      ("requires symlink support", "symlink-support"),
                      ("version solving failed", "dependency-resolution"),
                      ("navigation consistency check failed", "navigation-violation"),
                      ("building native assets failed", "native-assets")]
        category = next((label for needle, label in categories if needle in raw), "unclassified")
        raise GateError("Tool failed (exit " + str(int(result.returncode)) + "; " + category + "); detailed output suppressed for source privacy.")
    return result.stdout.decode("utf-8", errors="replace")


def fetch():
    require_secrets(["SOURCE_READ_TOKEN"])
    sha = checked_sha(os.environ["SOURCE_SHA"])
    source = ROOT / "source"
    require(not source.exists(), "Source directory already exists.")
    source.mkdir(mode=0o700)
    quiet(["git", "init", "--quiet", str(source)])
    quiet(["git", "config", "core.autocrlf", "false"], source)
    # Configuration exists only in this subprocess environment, never .git/config.
    env = os.environ.copy()
    credential = base64.b64encode(("x-access-token:" + env.pop("SOURCE_READ_TOKEN")).encode()).decode()
    env.update({"GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader", "GIT_CONFIG_VALUE_0": "AUTHORIZATION: basic " + credential, "GIT_CONFIG_KEY_1": "credential.helper", "GIT_CONFIG_VALUE_1": "", "GIT_TERMINAL_PROMPT": "0"})
    quiet(["git", "fetch", "--quiet", "--depth=1", "--no-tags", "https://github.com/" + SOURCE + ".git", sha], source, env)
    quiet(["git", "checkout", "--quiet", "--detach", "FETCH_HEAD"], source)
    require(quiet(["git", "rev-parse", "HEAD"], source).strip() == sha, "Fetched source SHA mismatch.")
    require(not (source / ".gitmodules").exists(), "Submodules require separate review.")
    print("Private source fetched at exact resolved SHA; credentials were not persisted.")


def property_escape(value):
    # Java Properties.load(InputStream) is ISO-8859-1 with unicode escapes.
    require(value and value == value.strip() and "\n" not in value and "\r" not in value, "Signing Secret has unsupported whitespace.")
    encoded = []
    for char in value:
        if char in "\\:= #!":
            encoded.append("\\" + char)
        elif not 32 <= ord(char) <= 126:
            for index in range(0, len(char.encode("utf-16-be")), 2):
                unit = char.encode("utf-16-be")[index:index + 2]
                encoded.append("\\u" + unit.hex())
        else:
            encoded.append(char)
    return "".join(encoded)


def metadata(candidate, sha, digest, platform="android"):
    version(candidate)
    checked_sha(sha)
    require(re.fullmatch(r"[0-9a-f]{64}", digest), "Invalid package digest.")
    require(platform in ("android", "windows"), "Invalid platform.")
    details = ({"application_id": POLICY["application_id"], "certificate_sha256": POLICY["certificate_sha256"], "abis": POLICY["abis"]}
               if platform == "android" else {"app_id": POLICY["windows_app_id"], "install_dir": POLICY["windows_install_dir"],
               "privileges": POLICY["windows_privileges"], "exe_name": POLICY["windows_exe"], "arch": POLICY["windows_arch"],
               "inno_setup_version": POLICY["inno_setup_version"], "authenticode": "NotSigned"})
    return {"schema": 3, "source_repository": SOURCE, "source_ref": SOURCE_REF, "source_sha": sha,
            "builder_repository": BUILDER, "builder_sha": os.environ["GITHUB_SHA"],
            "run_id": os.environ["GITHUB_RUN_ID"], "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
            "version": candidate, "platform": platform, "identity": details,
            "package_sha256": digest, "release_repository": DEST, "prerelease": False}


def apk_name(candidate):
    version(candidate)
    return f"emosonic_android_v{candidate}.apk"


def installer_name(candidate):
    version(candidate)
    return f"emosonic_windows_v{candidate}_setup.exe"


def package_name(candidate, platform):
    require(platform in ("android", "windows"), "Invalid platform.")
    return apk_name(candidate) if platform == "android" else installer_name(candidate)


def stable_tag(candidate):
    version(candidate)
    return "v" + candidate


def file_digest(path):
    require(path.is_file() and not path.is_symlink(), "Invalid artifact file.")
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def inspect_apk(path, candidate):
    sdk = Path(os.environ["ANDROID_HOME"]) / "build-tools" / POLICY["android_build_tools"]
    # Inspect only. Never install or execute the APK.
    signature = quiet([str(sdk / "apksigner"), "verify", "--verbose", "--print-certs", str(path)])
    signers = re.findall(r"^Signer #[0-9]+ certificate SHA-256 digest: ([0-9a-fA-F]{64})$", signature, re.MULTILINE)
    require([s.lower() for s in signers] == [POLICY["certificate_sha256"]], "APK signing certificate mismatch.")
    badging = quiet([str(sdk / "aapt"), "dump", "badging", str(path)])
    package = re.search(r"^package: name='([^']+)' versionCode='([^']+)' versionName='([^']+)'", badging, re.MULTILINE)
    require(package is not None, "APK package metadata missing.")
    name, build = candidate.split("+")
    require(package.groups() == (POLICY["application_id"], build, name), "APK package or version mismatch.")
    require("application-debuggable" not in badging, "Debuggable APK rejected.")
    with zipfile.ZipFile(path) as archive:
        entries = archive.namelist()
        require(len(entries) == len(set(entries)), "Duplicate APK entries rejected.")
        abis = sorted({n.split("/")[1] for n in entries if n.startswith("lib/") and n.endswith(".so")})
        require(abis == POLICY["abis"], "APK architecture set mismatch.")
        for entry in entries:
            lower = entry.lower()
            require(not entry.startswith("/") and ".." not in entry.split("/"), "Unsafe APK entry path.")
            require(not lower.endswith((".dart", ".jks", ".keystore", ".pem", ".key", ".pdb", ".symbols")) and ".git/" not in lower and ".dsym/" not in lower and lower.split("/")[-1] not in ("key.properties", ".env"), "Forbidden source, credential or debug artifact inside APK.")


def source_context():
    require_secrets(["DEFAULT_SERVER_URL"])
    candidate = os.environ["BUILD_VERSION"]
    version(candidate)
    sha = checked_sha(os.environ["SOURCE_SHA"])
    source = ROOT / "source"
    require(quiet(["git", "rev-parse", "HEAD"], source).strip() == sha, "Source SHA changed.")
    pubspec_path = source / "pubspec.yaml"
    require(pubspec_path.is_file() and not pubspec_path.is_symlink(), "Source pubspec.yaml must be a regular file.")
    pubspec = pubspec_path.read_text(encoding="utf-8")
    require(source_version(pubspec) == candidate, "Source version differs from the resolved pubspec version.")
    flutter = Path(shutil.which("flutter") or "missing").resolve()
    require(quiet(["git", "rev-parse", "HEAD"], flutter.parent.parent).strip() == POLICY["flutter_sha"], "Flutter SDK revision mismatch.")
    server = os.environ["DEFAULT_SERVER_URL"]
    parsed = urllib.parse.urlsplit(server)
    require(parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment, "DEFAULT_SERVER_URL must be HTTPS without credentials, query or fragment.")
    require(not any(ord(c) < 32 for c in server), "Invalid DEFAULT_SERVER_URL.")
    return source, candidate, sha, server


def build_env():
    return {k: v for k, v in os.environ.items() if k != "DEFAULT_SERVER_URL" and not any(word in k.upper() for word in ("TOKEN", "PASSWORD", "SECRET", "KEYSTORE", "KEY_ALIAS"))}


def codegen(source, env):
    for label, command in [
        ("Dependencies", ["flutter", "pub", "get"]),
        ("Navigation check", ["dart", "run", "scripts/check_navigation_consistency.dart"]),
        ("Code generation", ["dart", "run", "build_runner", "build", "--delete-conflicting-outputs"]),
    ]:
        print(label + " started (output suppressed).", flush=True)
        if os.name == "nt":
            flutter = Path(shutil.which("flutter") or "missing").resolve()
            if command[0] == "dart":
                runtime = flutter.parent / "cache/dart-sdk/bin/dart.exe"
                require(runtime.is_file() and not runtime.is_symlink(), "Bundled Windows Dart runtime is missing.")
                selected = Path(shutil.which("dart") or "missing").resolve()
                print("Windows PATH Dart matches bundled runtime: " + str(selected == runtime.resolve()), flush=True)
                command[0] = str(runtime)
            else:
                command[0] = str(flutter)
        quiet(command, source, env)


def native_android_contract(source, env):
    """Run production Java contracts and full Android compile before signing."""
    plugin = source / "third_party/just_audio"
    production = plugin / "android/src/main/java/com/ryanheise/just_audio/NativeStartGate.java"
    test = plugin / "android/src/test/java/com/ryanheise/just_audio/NativeStartGateTest.java"
    for path in (production, test):
        require(path.is_file() and not path.is_symlink()
                and path.resolve().is_relative_to(plugin.resolve()),
                "Reviewed native contract source is missing or invalid.")
    registration = source / ".flutter-plugins-dependencies"
    require(registration.is_file() and not registration.is_symlink(),
            "Flutter native plugin registration is missing.")
    plugins = json.loads(registration.read_text(encoding="utf-8"))["plugins"]["android"]
    selected = [entry for entry in plugins if entry.get("name") == "just_audio"]
    require(len(selected) == 1 and selected[0].get("native_build") is True
            and Path(selected[0].get("path", "")).resolve() == plugin.resolve(),
            "Android must compile the committed vendored just_audio plugin.")
    java_home = Path(env.get("JAVA_HOME", "missing"))
    javac, java = java_home / "bin/javac", java_home / "bin/java"
    require(javac.is_file() and java.is_file(), "Java compiler and runtime are required for native contracts.")
    require(NATIVE_CONTRACT_TEST_COUNT > 0, "Reviewed native test count has not been fixed.")
    print("Native Java contract compilation started (output suppressed).", flush=True)
    with tempfile.TemporaryDirectory(prefix=".native-contract-", dir=ROOT) as directory:
        classes = Path(directory)
        quiet([str(javac), "--release", "8", "-encoding", "UTF-8", "-d", str(classes),
               str(production), str(test)], source, env)
        for name in ("NativeStartGate", "NativeStartGateTest"):
            path = classes / ("com/ryanheise/just_audio/" + name + ".class")
            require(path.is_file() and not path.is_symlink() and path.stat().st_size > 0,
                    "Native contract compilation did not produce the required classes.")
        result = quiet([str(java), "-ea", "-cp", str(classes),
                        "com.ryanheise.just_audio.NativeStartGateTest"], source, env)
        expected = "PASS NativeStartGateTest: " + str(NATIVE_CONTRACT_TEST_COUNT) + " checks (deterministic JVM, no device claim)"
        require(result.strip() == expected, "Native contract success marker or test count mismatch.")
    print("Native Java contract tests passed: " + str(NATIVE_CONTRACT_TEST_COUNT) + " checks.", flush=True)
    print("Full Android debug compilation started (output suppressed).", flush=True)
    debug_apk = source / "build/app/outputs/flutter-apk/app-debug.apk"
    require(not debug_apk.exists(), "Pre-existing Android debug output rejected.")
    quiet(["flutter", "build", "apk", "--debug", "--target-platform=android-arm64"], source, env)
    require(debug_apk.is_file() and not debug_apk.is_symlink() and debug_apk.stat().st_size > 0,
            "Full Android debug compilation did not produce its APK.")
    print("Full Android debug compilation passed for the vendored native plugin.", flush=True)


def stage_package(path, candidate, sha, platform):
    dist = ROOT / "dist"
    dist.mkdir(mode=0o700)
    destination = dist / package_name(candidate, platform)
    shutil.copyfile(path, destination)
    digest = file_digest(destination)
    (dist / (destination.name + ".sha256")).write_text(digest + "  " + destination.name + "\n", encoding="ascii", newline="\n")
    (dist / (platform + "-manifest.json")).write_text(json.dumps(metadata(candidate, sha, digest, platform), indent=2) + "\n", encoding="utf-8", newline="\n")
    bundle(dist, candidate, sha, platform)


def build():
    require_secrets(["ANDROID_KEYSTORE_BASE64", "ANDROID_STORE_PASSWORD", "ANDROID_KEY_PASSWORD", "ANDROID_KEY_ALIAS"])
    source, candidate, sha, server = source_context()
    keyfile = source / "android/key.properties"
    keystore = source / "android/keystore/emosonic-release.jks"
    defines = source / "build-defines.json"
    require(not keyfile.exists() and not keystore.exists() and not defines.exists(), "Unexpected signing or define file in source.")
    # Every source/tool subprocess gets no PAT or signing Secret environment.
    clean_env = build_env()
    try:
        codegen(source, clean_env)
        native_android_contract(source, clean_env)
        keystore.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        keystore.write_bytes(base64.b64decode(os.environ["ANDROID_KEYSTORE_BASE64"], validate=True))
        keystore.chmod(0o600)
        keyfile.write_text("storeFile=keystore/emosonic-release.jks\n" + "\n".join(key + "=" + property_escape(os.environ[secret]) for key, secret in [("storePassword", "ANDROID_STORE_PASSWORD"), ("keyPassword", "ANDROID_KEY_PASSWORD"), ("keyAlias", "ANDROID_KEY_ALIAS")]) + "\n", encoding="ascii")
        keyfile.chmod(0o600)
        defines.write_text(json.dumps({"DEFAULT_SERVER_URL": server, "APP_UPDATE_SOURCE": "github", "GITHUB_RELEASE_REPOSITORY": DEST}), encoding="utf-8")
        defines.chmod(0o600)
        name, number = candidate.split("+")
        print("Release APK build started (output suppressed).", flush=True)
        quiet(["flutter", "build", "apk", "--release", "--target-platform=android-arm,android-arm64,android-x64", "--build-name=" + name, "--build-number=" + number, "--dart-define-from-file=" + str(defines)], source, clean_env)
        apk = source / "build/app/outputs/flutter-apk/app-release.apk"
        inspect_apk(apk, candidate)
        stage_package(apk, candidate, sha, "android")
    finally:
        for path in (keyfile, keystore, defines):
            path.unlink(missing_ok=True)


def bundle(directory, candidate, sha, platform="android"):
    name = package_name(candidate, platform)
    manifest = platform + "-manifest.json"
    require(directory.is_dir() and not directory.is_symlink(), "Artifact directory missing.")
    expected = {name, name + ".sha256", manifest}
    require({p.name for p in directory.iterdir()} == expected, "Unexpected or missing artifact files.")
    require(all(p.is_file() and not p.is_symlink() for p in directory.iterdir()), "Artifact links or directories rejected.")
    apk = directory / name
    require(0 < apk.stat().st_size < 512 * 1024 * 1024, "Package size outside allowed range.")
    require((directory / manifest).stat().st_size < 8192 and (directory / (name + ".sha256")).stat().st_size < 256, "Oversized metadata rejected.")
    digest = file_digest(apk)
    require((directory / (name + ".sha256")).read_text(encoding="ascii") == digest + "  " + name + "\n", "Package checksum mismatch.")
    require(json.loads((directory / manifest).read_text(encoding="utf-8")) == metadata(candidate, sha, digest, platform), "Artifact provenance mismatch.")
    return digest


def verify():
    candidate, sha = os.environ["BUILD_VERSION"], checked_sha(os.environ["SOURCE_SHA"])
    directory = ROOT / "incoming"
    digest = bundle(directory, candidate, sha)
    inspect_apk(directory / apk_name(candidate), candidate)
    output("apk_sha256", digest)
    print("Independent APK signature, package, version, ABI and provenance checks passed.")


def android_tools():
    """Use installed inspection tools; sdkmanager is not necessarily on PATH."""
    sdk = Path(os.environ["ANDROID_HOME"])
    build_tools = sdk / "build-tools" / POLICY["android_build_tools"]
    if not all((build_tools / name).is_file() for name in ("aapt", "apksigner")):
        manager = sdk / "cmdline-tools/latest/bin/sdkmanager"
        require(manager.is_file(), "Android SDK command-line tools are missing from the runner.")
        quiet([str(manager), "build-tools;" + POLICY["android_build_tools"]])
    require(all((build_tools / name).is_file() for name in ("aapt", "apksigner")),
              "Pinned Android inspection tools are missing after setup.")
    print("Pinned Android inspection tools are available.")


def windows_tool(name):
    paths = {"innounp": ROOT / ".tools/innounp/innounp.exe", "iscc": ROOT / ".tools/inno/{app}/ISCC.exe"}
    path = paths[name]
    require(file_digest(path) == POLICY[name + "_exe_sha256"], "Windows tool executable digest mismatch.")
    return path


def download_tool(url, path, digest):
    require(url.startswith("https://github.com/"), "Untrusted tool URL.")
    # Public pinned tools only. No PAT/header is supplied or forwarded.
    with urllib.request.urlopen(url, timeout=180) as response, path.open("wb") as target:
        shutil.copyfileobj(response, target)
    require(file_digest(path) == digest, "Downloaded Windows tool digest mismatch.")


def windows_tools():
    require(os.name == "nt", "Windows tools require a Windows runner.")
    target = ROOT / ".tools"
    target.mkdir(exist_ok=True)
    archive = target / "innounp.zip"
    download_tool(POLICY["innounp_url"], archive, POLICY["innounp_sha256"])
    with zipfile.ZipFile(archive) as zipped:
        for entry in zipped.namelist():
            require((target / "innounp" / entry).resolve().is_relative_to((target / "innounp").resolve()), "Unsafe tool archive path.")
        zipped.extractall(target / "innounp")
    unpacker = windows_tool("innounp")
    if os.environ.get("INSTALL_COMPILER") == "true":
        installer = target / "innosetup.exe"
        download_tool(POLICY["inno_setup_url"], installer, POLICY["inno_setup_sha256"])
        require(not (target / "inno").exists(), "Compiler directory already exists.")
        quiet([str(unpacker), "-x", "-b", "-q", "-o", "-d" + str(target / "inno"), str(installer)])
        windows_tool("iscc")
    print("Pinned Windows inspection/build tools are ready.")


def check_windows_source(source):
    # The owner trusts master code. This is an entrypoint compatibility check,
    # not a claim that string matching can sandbox an arbitrary build script.
    for name in ("build_windows.bat", "windows/installer/emosonic.iss"):
        path = source / name
        require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(source.resolve()), "Windows build entrypoint changed or missing; update builder compatibility.")


def windows_server(server):
    # The original batch entry point uses CALL (a second expansion pass).
    # Reject cmd metacharacters/percent escapes rather than interpolating them.
    require(re.fullmatch(r"https://[A-Za-z0-9._~:/-]+", server, re.ASCII), "Windows server URL contains unsupported batch characters.")
    return server


def build_windows():
    require(os.name == "nt", "Windows builds require a Windows runner.")
    source, candidate, sha, server = source_context()
    check_windows_source(source)
    compiler = windows_tool("iscc")
    # No source token, release token or Android signing Secrets enter the batch job.
    env = build_env()
    env.update({"DEFAULT_SERVER_URL": windows_server(server), "APP_UPDATE_SOURCE": "github", "GITHUB_RELEASE_REPOSITORY": DEST, "INNO_SETUP_COMPILER": str(compiler)})
    require(not (source / "build/windows").exists(), "Pre-existing Windows build output rejected.")
    codegen(source, env)
    print("Windows release build and original Inno packaging started (output suppressed).", flush=True)
    quiet(["cmd.exe", "/d", "/c", "build_windows.bat"], source, env)
    require(source_version((source / "pubspec.yaml").read_text(encoding="utf-8")) == candidate, "Source pubspec version changed during Windows build.")
    check_windows_source(source)
    package = source / "build/windows/installer" / installer_name(candidate)
    inspect_windows(package, candidate)
    stage_package(package, candidate, sha, "windows")


def setup_identity(script, candidate):
    # Recovered metadata is read as data, never executed or made public.
    fields = {}
    in_setup = False
    for line in script.splitlines():
        line = line.strip()
        if line.startswith("["):
            in_setup = line.lower() == "[setup]"
        elif in_setup and "=" in line and not line.startswith(";"):
            key, value = line.split("=", 1)
            key = key.lower()
            require(key not in fields, "Duplicate installer identity field.")
            fields[key] = value
    expected = {"appname": "EmoSonic", "appid": POLICY["windows_app_id"], "appversion": candidate.split("+")[0],
                "defaultdirname": POLICY["windows_install_dir"], "privilegesrequired": POLICY["windows_privileges"],
                "outputbasefilename": installer_name(candidate)[:-4]}
    require(all(fields.get(k) == v for k, v in expected.items()), "Windows installer upgrade identity or version mismatch.")


def pe_x64(path):
    with path.open("rb") as handle:
        header = handle.read(64)
        require(len(header) == 64 and header[:2] == b"MZ", "Invalid Windows executable header.")
        offset = struct.unpack_from("<I", header, 60)[0]
        require(64 <= offset <= 1024 * 1024, "Invalid PE offset.")
        handle.seek(offset)
        pe = handle.read(6)
    require(pe == b"PE\0\0\x64\x86", "Windows app must be x64 PE.")


def windows_version_info(path, installer):
    env = build_env()
    env.update({"INSPECT_EXE_PATH": str(path), "INSPECT_SETUP_PATH": str(installer)})
    # FileVersionInfo and signature parsing do not load/execute the app or installer.
    script = "$ErrorActionPreference='Stop'; $v=[System.Diagnostics.FileVersionInfo]::GetVersionInfo($env:INSPECT_EXE_PATH); @{file=$v.FileVersion; product=$v.ProductVersion; numeric=@($v.FileMajorPart,$v.FileMinorPart,$v.FileBuildPart,$v.FilePrivatePart); name=$v.ProductName; original=$v.OriginalFilename; debug=$v.IsDebug; signature=(Get-AuthenticodeSignature -LiteralPath $env:INSPECT_SETUP_PATH).Status.ToString()} | ConvertTo-Json -Compress"
    return json.loads(quiet(["pwsh", "-NoProfile", "-NonInteractive", "-Command", script], env=env))


def validate_windows_version(info, candidate):
    require(info == {"file": candidate, "product": candidate, "numeric": list(version(candidate)), "name": "EmoSonic", "original": POLICY["windows_exe"], "debug": False, "signature": "NotSigned"}, "Windows embedded executable version, identity or signing policy mismatch.")


def inspect_windows(path, candidate):
    version(candidate)
    require(os.name == "nt", "Windows inspection requires a Windows runner.")
    unpacker = windows_tool("innounp")
    require(path.is_file() and not path.is_symlink(), "Windows installer missing.")
    # Private extracted content is never uploaded. No setup switches /SILENT are used.
    with tempfile.TemporaryDirectory(prefix=".inspect-", dir=ROOT) as directory:
        extracted = Path(directory).resolve()
        require(extracted.is_relative_to(ROOT.resolve()), "Unsafe extraction directory.")
        quiet([str(unpacker), "-x", "-b", "-q", "-o", "-d" + str(extracted), str(path.resolve())])
        setup_identity((extracted / "install_script.iss").read_text(encoding="utf-8-sig"), candidate)
        require({p.name for p in extracted.iterdir()} == {"{app}", "install_script.iss"}, "Unexpected installer destinations.")
        app = extracted / "{app}"
        require(not app.is_symlink(), "Installer symlink rejected.")
        for file in app.rglob("*"):
            require(not file.is_symlink() and file.resolve().is_relative_to(app), "Unsafe extracted installer path.")
            lower = file.name.lower()
            require(not lower.endswith((".dart", ".jks", ".keystore", ".pem", ".key", ".pdb", ".symbols")) and lower not in (".git", ".env", "key.properties"), "Source, credential or debug file in Windows installer.")
        exe = app / POLICY["windows_exe"]
        require(exe.is_file(), "Windows application executable missing.")
        pe_x64(exe)
        for required in ("flutter_windows.dll", "data/app.so", "data/icudtl.dat", "data/flutter_assets/AssetManifest.bin"):
            require((app / required).is_file(), "Windows runtime payload is incomplete.")
        validate_windows_version(windows_version_info(exe, path), candidate)


def verify_windows():
    candidate, sha = os.environ["BUILD_VERSION"], checked_sha(os.environ["SOURCE_SHA"])
    directory = ROOT / "incoming"
    digest = bundle(directory, candidate, sha, "windows")
    inspect_windows(directory / installer_name(candidate), candidate)
    output("installer_sha256", digest)
    print("Independent Windows installer identity, embedded version, x64 and provenance checks passed.")


def release_files(directory, candidate, sha):
    require(directory.is_dir() and not directory.is_symlink() and {p.name for p in directory.iterdir()} == {"android", "windows"}, "Both platform bundles are required for stable publication.")
    digests = {platform: bundle(directory / platform, candidate, sha, platform) for platform in ("android", "windows")}
    require(digests["android"] == os.environ.get("VERIFIED_APK_SHA256") and digests["windows"] == os.environ.get("VERIFIED_INSTALLER_SHA256"), "Independent verifier digest mismatch.")
    paths = sorted(path for platform in ("android", "windows") for path in (directory / platform).iterdir())
    require(len(paths) == 6 and len({p.name for p in paths}) == 6, "Stable release asset set mismatch.")
    return paths, digests


def publish():
    require_secrets(["RELEASE_WRITE_TOKEN"])
    require(os.environ.get("RELEASE_MODE") == "publish-stable", "Stable publication was not requested.")
    token = os.environ["RELEASE_WRITE_TOKEN"]
    candidate, sha = os.environ["BUILD_VERSION"], checked_sha(os.environ["SOURCE_SHA"])
    directory = ROOT / "incoming"
    paths, digests = release_files(directory, candidate, sha)
    monotonic(candidate, history(token))
    tag = stable_tag(candidate)
    quoted_tag = urllib.parse.quote(tag, safe="")
    require(api(f"/repos/{DEST}/releases/tags/{quoted_tag}", token) is None, "Release already exists; overwrite prohibited.")
    require(api(f"/repos/{DEST}/git/ref/tags/{quoted_tag}", token) is None, "Tag already exists; overwrite prohibited.")
    latest = api(f"/repos/{DEST}/releases/latest", token)
    require(latest and not latest["prerelease"], "Stable latest baseline unavailable.")
    repo = api(f"/repos/{DEST}", token)
    require(repo and repo["full_name"] == DEST and not repo["private"], "Destination repository mismatch.")
    target = api(f"/repos/{DEST}/commits/{urllib.parse.quote(repo['default_branch'], safe='')}", token)
    require(target and SHA_RE.fullmatch(target["sha"]), "Destination target commit unavailable.")
    run_url = f"https://github.com/{BUILDER}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    body = (f"EmoSonic {candidate}: Android APK and Windows x64 installer, built from the same resolved master commit.\n\n"
            f"Source: {SOURCE}@{sha}\nBuilder: {BUILDER}@{os.environ['GITHUB_SHA']}\nRun: {run_url}\n\n"
            f"Android package: {POLICY['application_id']}\nAPK SHA-256: {digests['android']}\nWindows SHA-256: {digests['windows']}\n"
            "Both packages include matching .sha256 files. The stable tag and asset formats remain compatible with the existing in-app updater; end-to-end update acceptance is pending. No iOS build is included. GitHub source archives refer to the release repository, not the private app source.\n\n"
            "Validation limits: package build and independent binary inspection are automated checks only. Android/Windows installation and upgrade, real audio, offline cold start, OS media/process lifecycle, data compatibility and the M01-M15 device matrix remain NOT_RUN / PENDING_USER_VALIDATION. Back up application data before upgrading. Personal-lab acceptance is not production-readiness certification. No server deployment is included; strict-v2 server compatibility is not certified.\n")
    if sha == STABLE_PUSH_REQUEST["source_sha"] and candidate == STABLE_PUSH_REQUEST["version"]:
        body += ("\nChanges: adds source- and execution-scoped Android native playback-start acknowledgment using the actual Media3 Player.isPlaying observation, including fully buffered starts, inherited playback, stale/cancelled events, seeks and repeated-play handling. Durable completion/outbox isolation is preserved. Also merges the diagnostic-log sharing feature with bounded redaction of current/previous log snapshots and cancellation/concurrency coverage.\n"
                 "Native validation before release signing: production NativeStartGate.java and its committed standalone Java test harness compiled with Temurin 17 javac --release 8; 104 checks executed and passed with the exact success marker. A full Android debug build compiled the complete vendored just_audio plugin before signed release compilation. These are deterministic JVM contracts and actual Android compilation, not JUnit or real-device audio acceptance.\n"
                 "Source validation: complete Flutter suite 2,442/2,442 passed on the frozen snapshot verified byte-for-byte against this source commit. Full-project analysis, dependency resolution, code generation, navigation consistency, formatting, vendor provenance and whitespace checks passed without source changes. The four original regression probes passed 4/4; independent service/protocol probes passed 13/13 and independent native ordering checks passed. Independent source/protocol review found and verified fixes for inherited-playing reload, repeated-play pending-arm replacement and stale early-event starvation.\n"
                 "Android installation warning: this APK preserves package ID com.example.emosonic and the historical GitHub-release signing certificate. Compatibility with an already installed APK is not established. If Android reports a signature mismatch, STOP: do not uninstall the existing app or clear its data to force installation. Preserve downloaded music and application data. Real-device validation remains pending the user.\n")
    release = api(f"/repos/{DEST}/releases", token, "POST", {"tag_name": tag, "target_commitish": target["sha"], "name": "EmoSonic " + candidate, "body": body, "draft": True, "prerelease": False, "make_latest": "false"})
    release_id = release["id"]
    require(isinstance(release_id, int), "Invalid draft release response.")
    # Failure leaves a draft for owner inspection; never delete or overwrite assets.
    for path in paths:
        response = api(f"/repos/{DEST}/releases/{release_id}/assets?name={urllib.parse.quote(path.name, safe='')}", token, "POST", path.read_bytes(), upload=True)
        require(response.get("name") == path.name and response.get("size") == path.stat().st_size and response.get("digest") == "sha256:" + file_digest(path), "Uploaded asset digest mismatch; draft retained.")
    remote = api(f"/repos/{DEST}/releases/{release_id}", token)
    require(remote and remote["draft"] and not remote["prerelease"] and remote["tag_name"] == tag, "Draft state changed unexpectedly.")
    expected_assets = {p.name: (p.stat().st_size, "sha256:" + file_digest(p)) for p in paths}
    actual_assets = {a["name"]: (a["size"], a["digest"]) for a in remote["assets"]}
    require(len(remote["assets"]) == 6 and actual_assets == expected_assets, "Remote asset set or digest mismatch; draft retained.")
    current_tag = api(f"/repos/{DEST}/git/ref/tags/{quoted_tag}", token)
    require(current_tag is None or (current_tag["object"]["type"] == "commit" and current_tag["object"]["sha"] == target["sha"]), "Release tag changed concurrently; draft retained.")
    monotonic(candidate, history(token, exclude_id=release_id, exclude_tag=tag))
    require(api(f"/repos/{DEST}/releases/latest", token)["id"] == latest["id"], "Stable release changed concurrently; draft retained.")
    final = api(f"/repos/{DEST}/releases/{release_id}", token, "PATCH", {"draft": False, "prerelease": False, "make_latest": "true"})
    require(not final["draft"] and not final["prerelease"], "Stable release publication could not be verified.")
    require(api(f"/repos/{DEST}/releases/latest", token)["id"] == release_id, "Stable latest promotion not verified; owner inspection required.")
    print("Verified Android and Windows packages published as stable latest.")


def cleanup():
    # Only this job's dedicated source directory, never a parent/workspace path.
    source = ROOT / "source"
    if source.is_symlink():
        source.unlink()
    elif source.exists():
        require(source.resolve().is_relative_to(ROOT.resolve()), "Unsafe source cleanup path.")
        def remove_readonly(function, path, exc):
            require(Path(path).resolve().is_relative_to(source.resolve()), "Unsafe cleanup retry path.")
            os.chmod(path, 0o700)
            function(path)
        shutil.rmtree(source, onerror=remove_readonly)


def main():
    try:
        context()
        require(len(sys.argv) == 2 and sys.argv[1] in ("prepare", "fetch", "build", "verify", "android_tools", "windows_tools", "build_windows", "verify_windows", "publish", "cleanup"), "Invalid pipeline stage.")
        globals()[sys.argv[1]]()
    except GateError as error:
        print("ERROR: " + str(error), file=sys.stderr)
        return 1
    except Exception:
        print("ERROR: Pipeline failed; sensitive details suppressed. Reproduce privately for diagnosis.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

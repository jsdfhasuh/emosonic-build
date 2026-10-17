"""Restricted Android builder. Stdlib only; never print subprocess/API bodies."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "policy.json").read_text(encoding="utf-8"))
SOURCE = "jsdfhasuh/emosonic"
DEST = "jsdfhasuh/emosonic-releases"
BUILDER = "jsdfhasuh/emosonic-build"
VERSION_RE = re.compile(r"(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})\+([1-9][0-9]{0,9})", re.ASCII)
SHA_RE = re.compile(r"[0-9a-f]{40}", re.ASCII)


class GateError(Exception):
    """Only fixed, non-sensitive messages may be passed to this exception."""


def require(condition, message):
    if not condition:
        raise GateError(message)


def version(value):
    require(isinstance(value, str) and VERSION_RE.fullmatch(value), "Invalid version: expected X.Y.Z+BUILD.")
    parts = tuple(map(int, VERSION_RE.fullmatch(value).groups()))
    require(parts[3] <= 2_100_000_000, "Android build number exceeds allowed limit.")
    return parts


def ref_input(value):
    require(isinstance(value, str) and 0 < len(value) <= 200, "Invalid source ref.")
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./-]*", value, re.ASCII), "Invalid source ref.")
    require(".." not in value and "//" not in value and not value.endswith(("/", ".", ".lock")), "Invalid source ref.")
    return value


def checked_sha(value):
    require(isinstance(value, str) and SHA_RE.fullmatch(value), "Invalid source SHA.")
    require(value in POLICY["trusted_source_shas"], "Source SHA has not been reviewed in policy.json.")
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
        require(current[:3] >= old[:3] and current[3] > old[3], "Version rollback, reused build number, or release conflict.")


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
    require(re.fullmatch(r"[a-z_]+", name) and "\n" not in value and "\r" not in value, "Unsafe workflow output.")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def require_secrets(names):
    for name in names:
        require(bool(os.environ.get(name)), "Required credential is missing; configure the documented Secrets.")


def context():
    require(POLICY["source_repository"] == SOURCE and POLICY["release_repository"] == DEST and POLICY["builder_repository"] == BUILDER, "Repository policy mismatch.")
    require(os.environ.get("GITHUB_REPOSITORY") == BUILDER, "Untrusted builder repository.")
    require(os.environ.get("GITHUB_REF") == "refs/heads/main", "Only trusted main may run.")
    require(os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch", "Only manual workflow_dispatch may run.")
    require(SHA_RE.fullmatch(os.environ.get("GITHUB_SHA", "")), "Invalid builder SHA.")
    require(re.fullmatch(r"[1-9][0-9]*", os.environ.get("GITHUB_RUN_ID", "")), "Invalid workflow run ID.")
    require(re.fullmatch(r"[1-9][0-9]*", os.environ.get("GITHUB_RUN_ATTEMPT", "")), "Invalid workflow attempt.")


def prepare():
    require_secrets(["SOURCE_READ_TOKEN"])
    candidate = os.environ["BUILD_VERSION"]
    version(candidate)
    require(os.environ.get("RELEASE_MODE") in ("build-only", "publish-prerelease"), "Invalid release mode.")
    ref = ref_input(os.environ["SOURCE_REF"])
    result = api(f"/repos/{SOURCE}/commits/{urllib.parse.quote(ref, safe='')}", os.environ["SOURCE_READ_TOKEN"])
    require(isinstance(result, dict), "Source ref could not be resolved.")
    sha = checked_sha(result.get("sha"))
    monotonic(candidate, history(os.environ.get("GITHUB_TOKEN")))
    output("source_sha", sha)
    output("version", candidate)
    output("apk_name", f"emosonic_android_v{candidate}.apk")
    print("Source ref resolved to reviewed SHA; version gates passed.")


def quiet(args, cwd=None, env=None):
    # Compiler stderr can contain private source snippets, paths and secrets.
    # No retained log and no traceback containing argv, stderr or API response.
    try:
        result = subprocess.run(args, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    except OSError:
        raise GateError("Required tool is unavailable.") from None
    require(result.returncode == 0, "Tool failed; detailed output suppressed for source privacy.")
    return result.stdout.decode("utf-8", errors="replace")


def fetch():
    require_secrets(["SOURCE_READ_TOKEN"])
    sha = checked_sha(os.environ["SOURCE_SHA"])
    source = ROOT / "source"
    require(not source.exists(), "Source directory already exists.")
    source.mkdir(mode=0o700)
    quiet(["git", "init", "--quiet", str(source)])
    # Configuration exists only in this subprocess environment, never .git/config.
    env = os.environ.copy()
    credential = base64.b64encode(("x-access-token:" + env.pop("SOURCE_READ_TOKEN")).encode()).decode()
    env.update({"GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader", "GIT_CONFIG_VALUE_0": "AUTHORIZATION: basic " + credential, "GIT_CONFIG_KEY_1": "credential.helper", "GIT_CONFIG_VALUE_1": "", "GIT_TERMINAL_PROMPT": "0"})
    quiet(["git", "fetch", "--quiet", "--depth=1", "--no-tags", "https://github.com/" + SOURCE + ".git", sha], source, env)
    quiet(["git", "checkout", "--quiet", "--detach", "FETCH_HEAD"], source)
    require(quiet(["git", "rev-parse", "HEAD"], source).strip() == sha, "Fetched source SHA mismatch.")
    require(not (source / ".gitmodules").exists(), "Submodules require separate review.")
    print("Private source fetched at exact reviewed SHA; credentials were not persisted.")


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


def metadata(candidate, sha, digest):
    version(candidate)
    checked_sha(sha)
    require(re.fullmatch(r"[0-9a-f]{64}", digest), "Invalid APK digest.")
    return {"schema": 1, "source_repository": SOURCE, "source_sha": sha,
            "builder_repository": BUILDER, "builder_sha": os.environ["GITHUB_SHA"],
            "run_id": os.environ["GITHUB_RUN_ID"], "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
            "version": candidate, "application_id": POLICY["application_id"],
            "certificate_sha256": POLICY["certificate_sha256"], "abis": POLICY["abis"],
            "apk_sha256": digest, "release_repository": DEST, "prerelease": True}


def apk_name(candidate):
    version(candidate)
    return f"emosonic_android_v{candidate}.apk"


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


def build():
    names = ["ANDROID_KEYSTORE_BASE64", "ANDROID_STORE_PASSWORD", "ANDROID_KEY_PASSWORD", "ANDROID_KEY_ALIAS", "DEFAULT_SERVER_URL"]
    require_secrets(names)
    candidate = os.environ["BUILD_VERSION"]
    selected = version(candidate)
    sha = checked_sha(os.environ["SOURCE_SHA"])
    source = ROOT / "source"
    require(quiet(["git", "rev-parse", "HEAD"], source).strip() == sha, "Source SHA changed.")
    pubspec = (source / "pubspec.yaml").read_text(encoding="utf-8")
    matches = re.findall(r"^version:\s*([^\s#]+)\s*(?:#.*)?$", pubspec, re.MULTILINE)
    require(len(matches) == 1, "Source version is ambiguous.")
    original = version(matches[0])
    require(selected[:3] >= original[:3] and selected[3] >= original[3], "Requested version predates source version.")
    flutter = Path(shutil.which("flutter") or "missing").resolve()
    require(quiet(["git", "rev-parse", "HEAD"], flutter.parent.parent).strip() == POLICY["flutter_sha"], "Flutter SDK revision mismatch.")
    server = os.environ["DEFAULT_SERVER_URL"]
    parsed = urllib.parse.urlsplit(server)
    require(parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment, "DEFAULT_SERVER_URL must be HTTPS without credentials, query or fragment.")
    require(not any(ord(c) < 32 for c in server), "Invalid DEFAULT_SERVER_URL.")
    keyfile = source / "android/key.properties"
    keystore = source / "android/keystore/emosonic-release.jks"
    defines = source / "build-defines.json"
    require(not keyfile.exists() and not keystore.exists() and not defines.exists(), "Unexpected signing or define file in source.")
    # Every source/tool subprocess gets no PAT or signing Secret environment.
    clean_env = {k: v for k, v in os.environ.items() if k not in names and not any(word in k.upper() for word in ("TOKEN", "PASSWORD", "SECRET"))}
    try:
        for label, command in [
            ("Dependencies", ["flutter", "pub", "get"]),
            ("Navigation check", ["dart", "run", "scripts/check_navigation_consistency.dart"]),
            ("Code generation", ["dart", "run", "build_runner", "build", "--delete-conflicting-outputs"]),
        ]:
            print(label + " started (output suppressed).", flush=True)
            quiet(command, source, clean_env)
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
        dist = ROOT / "dist"
        dist.mkdir(mode=0o700)  # Fail if an existing output directory is present.
        destination = dist / apk_name(candidate)
        shutil.copyfile(apk, destination)
        digest = file_digest(destination)
        (dist / (destination.name + ".sha256")).write_text(digest + "  " + destination.name + "\n", encoding="ascii")
        (dist / "manifest.json").write_text(json.dumps(metadata(candidate, sha, digest), indent=2) + "\n", encoding="utf-8")
        bundle(dist, candidate, sha)
    finally:
        for path in (keyfile, keystore, defines):
            path.unlink(missing_ok=True)


def bundle(directory, candidate, sha):
    name = apk_name(candidate)
    require(directory.is_dir() and not directory.is_symlink(), "Artifact directory missing.")
    expected = {name, name + ".sha256", "manifest.json"}
    require({p.name for p in directory.iterdir()} == expected, "Unexpected or missing artifact files.")
    require(all(p.is_file() and not p.is_symlink() for p in directory.iterdir()), "Artifact links or directories rejected.")
    apk = directory / name
    require(0 < apk.stat().st_size < 512 * 1024 * 1024, "APK size outside allowed range.")
    require((directory / "manifest.json").stat().st_size < 8192 and (directory / (name + ".sha256")).stat().st_size < 256, "Oversized metadata rejected.")
    digest = file_digest(apk)
    require((directory / (name + ".sha256")).read_text(encoding="ascii") == digest + "  " + name + "\n", "APK checksum mismatch.")
    require(json.loads((directory / "manifest.json").read_text(encoding="utf-8")) == metadata(candidate, sha, digest), "Artifact provenance mismatch.")
    return digest


def verify():
    candidate, sha = os.environ["BUILD_VERSION"], checked_sha(os.environ["SOURCE_SHA"])
    directory = ROOT / "incoming"
    digest = bundle(directory, candidate, sha)
    inspect_apk(directory / apk_name(candidate), candidate)
    output("apk_sha256", digest)
    print("Independent APK signature, package, version, ABI and provenance checks passed.")


def publish():
    require_secrets(["RELEASE_WRITE_TOKEN"])
    require(os.environ.get("RELEASE_MODE") == "publish-prerelease", "Publishing was not requested.")
    token = os.environ["RELEASE_WRITE_TOKEN"]
    candidate, sha = os.environ["BUILD_VERSION"], checked_sha(os.environ["SOURCE_SHA"])
    directory = ROOT / "incoming"
    digest = bundle(directory, candidate, sha)
    require(digest == os.environ.get("VERIFIED_APK_SHA256"), "Verified job digest mismatch.")
    monotonic(candidate, history(token))
    tag = "android-v" + candidate
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
    body = (f"Android-only prerelease {candidate}. Manual installation only; stable latest is unchanged.\n\n"
            f"Source: {SOURCE}@{sha}\nBuilder: {BUILDER}@{os.environ['GITHUB_SHA']}\nRun: {run_url}\n\n"
            f"Package: {POLICY['application_id']}\nAPK SHA-256: {digest}\n"
            "No Windows or iOS build is included. Source archives generated by GitHub refer to the release repository, not the private app source.\n")
    release = api(f"/repos/{DEST}/releases", token, "POST", {"tag_name": tag, "target_commitish": target["sha"], "name": "EmoSonic Android " + candidate, "body": body, "draft": True, "prerelease": True, "make_latest": "false"})
    release_id = release["id"]
    require(isinstance(release_id, int), "Invalid draft release response.")
    # Failure leaves a draft for owner inspection; never delete or overwrite assets.
    for path in sorted(directory.iterdir()):
        response = api(f"/repos/{DEST}/releases/{release_id}/assets?name={urllib.parse.quote(path.name, safe='')}", token, "POST", path.read_bytes(), upload=True)
        require(response.get("name") == path.name and response.get("size") == path.stat().st_size and response.get("digest") == "sha256:" + file_digest(path), "Uploaded asset digest mismatch; draft retained.")
    remote = api(f"/repos/{DEST}/releases/{release_id}", token)
    require(remote and remote["draft"] and remote["prerelease"] and remote["tag_name"] == tag, "Draft state changed unexpectedly.")
    require({a["name"] for a in remote["assets"]} == {p.name for p in directory.iterdir()}, "Unexpected remote assets; draft retained.")
    current_tag = api(f"/repos/{DEST}/git/ref/tags/{quoted_tag}", token)
    require(current_tag is None or (current_tag["object"]["type"] == "commit" and current_tag["object"]["sha"] == target["sha"]), "Release tag changed concurrently; draft retained.")
    monotonic(candidate, history(token, exclude_id=release_id, exclude_tag=tag))
    require(api(f"/repos/{DEST}/releases/latest", token)["id"] == latest["id"], "Stable release changed concurrently; draft retained.")
    final = api(f"/repos/{DEST}/releases/{release_id}", token, "PATCH", {"draft": False, "prerelease": True, "make_latest": "false"})
    require(not final["draft"] and final["prerelease"], "Release publication could not be verified.")
    require(api(f"/repos/{DEST}/releases/latest", token)["id"] == latest["id"], "Stable latest changed; owner inspection required.")
    print("Android prerelease published; stable latest preserved.")


def cleanup():
    # Only this job's dedicated source directory, never a parent/workspace path.
    source = ROOT / "source"
    if source.is_symlink():
        source.unlink()
    elif source.exists():
        shutil.rmtree(source)


def main():
    try:
        context()
        require(len(sys.argv) == 2 and sys.argv[1] in ("prepare", "fetch", "build", "verify", "publish", "cleanup"), "Invalid pipeline stage.")
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

"""Pin and prove disposable read-only Follow lifecycle observations."""
import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LAB = 'tool/native_playback_mac/run_lab.py'
LAB_MAIN = 'tool/native_playback_mac/main.dart'
MAIN_BEFORE_SHA256 = '7e4b804a9eaeeec929768ddd9ce9a5479639f73f443a8f3e6693916e59565833'
MAIN_AFTER_SHA256 = 'f8781ae5077924daebc0908500f79e57ee9a80af8e9d25d474468651563d2af0'
LOG_OLD = b'  await Logger.setLogLevel(LogLevel.warning);\n'
LOG_NEW = b'  await Logger.setLogLevel(LogLevel.debug);\n'
STATE = '.native_follow_lifecycle/manifest.json'
BEFORE_SHA256 = 'af4053d6801cbd18e20f777b4a952f8dcf7822a1fbe1c4e0965211c42d431b82'
AFTER_HARNESS_SHA256 = 'a283fefe723aa6002f21836bb159c64d3d060a8a23e778da4f3fcc6a5e4cc5a6'
PAYLOAD_HASHES = {'follow_lifecycle_observation.py': '61f845892a17587b30e223289a8899cbeab38861d9fcaba08057a03186c42ad2', 'follow_server_observation.py': '5426d798c3b65fe46652814f3433657bb6e315d0b4345c214555bc4e2479e4cc'}
OBSERVER_CALLS = (
    'begin_follow_lifecycle(self, context, follower_original, native_follow_task_ready)',
    'observe_follow_command(self, _follow_response)',
    'observe_follow_wait(self, stage, states)',
)
CALL_AST = tuple(ast.dump(ast.parse(source).body[0].value) for source in OBSERVER_CALLS)
IMPORT = 'from follow_lifecycle_observation import begin_follow_lifecycle, observe_follow_command, observe_follow_wait, finish_follow_lifecycle\n'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('Lifecycle observation anchor changed')
    return text.replace(before, after, 1)


class OriginalProjection(ast.NodeTransformer):
    """Remove only the exact known observer syntax, not controls/assertions."""
    def visit_ImportFrom(self, node):
        if ast.dump(node) == ast.dump(ast.parse(IMPORT).body[0]):
            return None
        return node

    def visit_Expr(self, node):
        if isinstance(node.value, ast.Call) and ast.dump(node.value) in CALL_AST:
            return None
        return self.generic_visit(node)

    def visit_Assign(self, node):
        if (len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == '_follow_response'):
            expected = ast.parse("follower.command('follow', contextId=context)").body[0].value
            if ast.dump(node.value) != ast.dump(expected):
                raise ValueError('Lifecycle command behavior changed')
            return ast.Expr(value=node.value)
        expected = ast.parse("state = Path(temporary).resolve(strict=True) / 'server'").body[0]
        if ast.dump(node) == ast.dump(expected):
            return ast.parse("state = Path(temporary) / 'server'").body[0]
        return self.generic_visit(node)

    def visit_Dict(self, node):
        keep = []
        for key, value in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and key.value == 'followLifecycle':
                expected = ast.parse('finish_follow_lifecycle(self)').body[0].value
                if ast.dump(value) != ast.dump(expected):
                    raise ValueError('Lifecycle summary behavior changed')
            else:
                keep.append((key, value))
        node.keys, node.values = [a for a, _ in keep], [b for _, b in keep]
        return self.generic_visit(node)


def prove_controls_unchanged(original, patched):
    before, after = ast.parse(original), ast.parse(patched)
    if [ast.dump(n) for n in ast.walk(before) if isinstance(n, ast.Assert)] != [ast.dump(n) for n in ast.walk(after) if isinstance(n, ast.Assert)]:
        raise ValueError('Lifecycle assertion set changed')
    calls = [ast.dump(n) for n in ast.walk(after) if isinstance(n, ast.Call)]
    if any(calls.count(item) != 1 for item in CALL_AST):
        raise ValueError('Lifecycle observation call count changed')
    restored = OriginalProjection().visit(copy.deepcopy(after))
    if ast.dump(before) != ast.dump(restored):
        raise ValueError('Lifecycle original control behavior changed')
    return {'allOriginalAssertionsUnchanged': True, 'allOriginalControlsUnchanged': True}


def _transform_harness(original):
    if digest(original) != BEFORE_SHA256:
        raise ValueError('Lifecycle source pin changed')
    text = original.decode('utf-8')
    anchor = 'from urllib.error import HTTPError, URLError\n'
    text = once(text, anchor, anchor + IMPORT)
    anchor = "            follower.command('follow', contextId=context)\n"
    text = once(text, anchor, "            begin_follow_lifecycle(self, context, follower_original, native_follow_task_ready)\n"
        "            _follow_response = follower.command('follow', contextId=context)\n"
        "            observe_follow_command(self, _follow_response)\n")
    anchor = '                if reject_terminal_handoff:\n'
    text = once(text, anchor, '                observe_follow_wait(self, stage, states)\n                if reject_terminal_handoff:\n')
    anchor = "                          'waitObservation': getattr(self, 'wait_observation', {}),\n"
    text = once(text, anchor, anchor + "                          'followLifecycle': finish_follow_lifecycle(self),\n")
    text = once(text, "state = Path(temporary) / 'server'", "state = Path(temporary).resolve(strict=True) / 'server'")
    result = text.encode('utf-8')
    prove_controls_unchanged(original, result)
    return result


def patch_harness(original):
    result = _transform_harness(original)
    if digest(result) != AFTER_HARNESS_SHA256:
        raise ValueError('Lifecycle transformed hash changed')
    return result


def patch_lab_logging(original):
    if digest(original) != MAIN_BEFORE_SHA256 or original.count(LOG_OLD) != 1:
        raise ValueError('Lifecycle lab logging baseline changed')
    updated = original.replace(LOG_OLD, LOG_NEW, 1)
    if updated.count(LOG_NEW) != 1 or updated.replace(LOG_NEW, LOG_OLD, 1) != original or digest(updated) != MAIN_AFTER_SHA256:
        raise ValueError('Lifecycle lab logging roundtrip changed')
    return updated


def payload(name):
    data = (ROOT / 'native_follow_lifecycle_payload' / name).read_bytes()
    if digest(data) != PAYLOAD_HASHES[name]:
        raise ValueError('Lifecycle packaged observer changed')
    ast.parse(data)
    return data


def checked(repo, relative, *, new=False):
    repo, path = Path(repo), Path(repo) / relative
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.resolve().is_relative_to(repo.resolve()):
        raise ValueError('Lifecycle source scope refused')
    if new:
        if path.exists() or not path.parent.is_dir():
            raise ValueError('Lifecycle destination is not fresh')
    elif not path.is_file():
        raise ValueError('Lifecycle source unavailable')
    return path


def expected_manifest():
    return {'status': 'prepared', 'productionRepositoryMutation': False,
        'disposableReadOnlyObservations': True, 'labOnlyDiagnosticLogging': True, 'allOriginalAssertionsUnchanged': True,
        'allOriginalControlsUnchanged': True, 'files': {LAB: {'before': BEFORE_SHA256, 'after': AFTER_HARNESS_SHA256},
            LAB_MAIN: {'before': MAIN_BEFORE_SHA256, 'after': MAIN_AFTER_SHA256}},
        'added': {'tool/native_playback_mac/' + name: checksum for name, checksum in PAYLOAD_HASHES.items()},
        'payloads': PAYLOAD_HASHES}


def apply(repo):
    lab = checked(repo, LAB)
    main = checked(repo, LAB_MAIN)
    updated_main = patch_lab_logging(main.read_bytes())
    state_root = checked(repo, '.native_follow_lifecycle', new=True)
    added = {name: checked(repo, 'tool/native_playback_mac/' + name, new=True) for name in PAYLOAD_HASHES}
    source = lab.read_bytes()
    transformed = patch_harness(source)
    observers = {name: payload(name) for name in PAYLOAD_HASHES}
    # Validate every source and destination before any write.
    state_root.mkdir()
    for name, data in observers.items():
        added[name].write_bytes(data)
    lab.write_bytes(transformed)
    main.write_bytes(updated_main)
    manifest = expected_manifest()
    (state_root / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest


def verify(repo, *, payload_only=False, timing_observation=False):
    if type(timing_observation) is not bool:
        raise ValueError('Lifecycle timing observation mode refused')
    expected_harness = AFTER_HARNESS_SHA256
    if timing_observation:
        import native_seek_anchor_observation as timing
        if timing.HARNESS_SHA != AFTER_HARNESS_SHA256:
            raise ValueError('Lifecycle timing baseline chain changed')
        timing.verify_prepared(repo, require_harness=not payload_only)
        expected_harness = timing.AFTER[LAB]
    for name in PAYLOAD_HASHES:
        payload(name)
        if digest(checked(repo, 'tool/native_playback_mac/' + name).read_bytes()) != PAYLOAD_HASHES[name]:
            raise ValueError('Lifecycle disposable observer changed')
    manifest = json.loads(checked(repo, STATE).read_text())
    flags = ('productionRepositoryMutation', 'disposableReadOnlyObservations', 'labOnlyDiagnosticLogging',
             'allOriginalAssertionsUnchanged', 'allOriginalControlsUnchanged')
    if type(manifest) is not dict or manifest != expected_manifest() or any(type(manifest.get(k)) is not bool for k in flags):
        raise ValueError('Lifecycle manifest changed')
    main = checked(repo, LAB_MAIN).read_bytes()
    if main.count(LOG_NEW) != 1 or patch_lab_logging(main.replace(LOG_NEW, LOG_OLD, 1)) != main:
        raise ValueError('Lifecycle lab logging instrumentation changed')
    # After stream attribution, that helper checks the composed harness against
    # this independently pinned AFTER_HARNESS_SHA256. Do not derive a runtime pin.
    if not payload_only and digest(checked(repo, LAB).read_bytes()) != expected_harness:
        raise ValueError('Lifecycle prepared harness changed')
    return manifest


def verify_prepared(source_repo, require_harness=True, *, timing_observation=False):
    if type(require_harness) is not bool:
        raise ValueError('Lifecycle verification mode refused')
    return verify(source_repo, payload_only=not require_harness, timing_observation=timing_observation)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=('apply', 'verify', 'verify-payload'))
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--timing-observation', action='store_true')
    args = parser.parse_args()
    if args.operation == 'apply':
        if args.timing_observation:
            parser.error('timing observation is verification-only')
        apply(args.repo)
    else:
        verify(args.repo, payload_only=args.operation == 'verify-payload', timing_observation=args.timing_observation)


if __name__ == '__main__':
    main()

def instrument_seek_observability(target):
    """Read-only getters in the already-copied, exact reviewed just_audio source."""
    relative = 'darwin/just_audio/Sources/just_audio/'
    paths = {'AudioPlayer.h': target / relative / 'include/just_audio/AudioPlayer.h',
             'AudioPlayer.m': target / relative / 'AudioPlayer.m'}
    expected = {'AudioPlayer.h': 'c8c6df3bc07f10677e0afbeb447c88da2a704b2c8323769247f78768c6a43138',
        'AudioPlayer.m': 'ecec29e1f913f0dca944ca3fb2e45a7ad96a138391af59f99ca3f46dfd5b65b3'}
    originals = {}
    for name, path in paths.items():
        if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
            raise RuntimeError('Native seek observation source path refused')
        originals[name] = path.read_bytes()
        if hashlib.sha256(originals[name]).hexdigest() != expected[name]:
            raise RuntimeError('Native seek observation source pin changed')
    header_anchor = '@property (readonly, nonatomic) float speed;'
    getter_anchor = '- (float)speed {\n    return _speed;\n}'
    declarations = '\n@property (readonly, nonatomic) BOOL labSeekInProgress;\n@property (readonly, nonatomic) BOOL labPlayingIntent;'
    getters = '\n\n- (BOOL)labSeekInProgress {\n    return CMTIME_IS_VALID(_seekPos);\n}\n\n- (BOOL)labPlayingIntent {\n    return _playing;\n}'
    patches = {'AudioPlayer.h': (header_anchor, declarations), 'AudioPlayer.m': (getter_anchor, getters)}
    updated = {}
    for name, (anchor, addition) in patches.items():
        text = originals[name].decode('utf-8')
        if text.count(anchor) != 1 or 'labSeekInProgress' in text or 'labPlayingIntent' in text:
            raise RuntimeError('Native seek observation anchor changed')
        updated[name] = text.replace(anchor, anchor + addition, 1).encode('utf-8')
        if updated[name].replace(addition.encode('utf-8'), b'', 1) != originals[name]:
            raise RuntimeError('Native seek observation roundtrip failed')
    for name, path in paths.items():
        path.write_bytes(updated[name])
    return {name: {'before': expected[name], 'after': hashlib.sha256(updated[name]).hexdigest()}
            for name in paths}

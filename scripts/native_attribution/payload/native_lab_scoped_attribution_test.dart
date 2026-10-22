import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:drift/native.dart';
import 'package:emosonic/data/models/models.dart';
import 'package:emosonic/data/models/offline_resource.dart';
import 'package:emosonic/data/services/audio_asset_repository.dart';
import 'package:emosonic/data/services/offline_store_repository.dart';
import 'package:emosonic/data/services/subsonic/subsonic_api_client.dart';
import 'package:emosonic/providers/account_session_providers.dart';
import 'package:emosonic/providers/api_client_providers.dart';
import 'package:emosonic/services/audio_source_resolver.dart';
import 'package:emosonic/services/media_stream_strategy_resolver.dart';
import 'package:emosonic/services/playback_source_policy.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import '../../tool/native_playback_mac/main.dart' show LabSubsonicApiClient;
import 'package:emosonic/providers/native_lab_scoped_api_client.dart';

const _config = ServerConfig(
  id: 'native-lab-attribution-test',
  name: 'Owned test fixture',
  url: 'http://127.0.0.1:31337',
  username: 'fixture-account',
  password: 'fixture-password-not-a-user-secret',
  apiEndpoint: 'rest',
);
const _song = Song(
  id: 'fixture-track-a', title: 'Fixture A', albumId: '', albumName: '',
  artistId: '', artistName: '', duration: 5,
);

Matcher _failure(OfflineFailureKind kind) => isA<OfflineFailure>()
    .having((error) => error.kind, 'kind', kind);
NativeLabStreamAttribution _scope({String instance = 'target'}) =>
    NativeLabStreamAttribution(instance: instance,
        fixtureStreamUri: Uri.parse('${_config.url}/rest/stream'),
        trackIds: {_song.id});

void _expectRealAuthAndRoute(String value, {required bool marked}) {
  final uri = Uri.parse(value);
  expect(uri.scheme, 'http');
  expect(uri.host, '127.0.0.1');
  expect(uri.port, 31337);
  expect(uri.path, '/rest/stream');
  final query = uri.queryParameters;
  expect(query['id'], _song.id);
  expect(query['u'], _config.username);
  expect(query['v'], '1.16.1');
  expect(query['c'], 'emosonic');
  expect(query['s'], isNotEmpty);
  expect(query['t'], md5.convert(utf8.encode('${_config.password}${query['s']}')).toString());
  expect(query.containsKey('nativeLabInstance'), marked);
  if (marked) expect(query['nativeLabInstance'], 'target');
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final expected = Platform.environment['EMOSONIC_NATIVE_LAB_EXPECT_ATTRIBUTION'];
  final patched = expected == 'patched';

  test('actual scoped factory and resolver attribution expectation is explicit', () {
    expect(expected, isIn(['baseline', 'patched']));
  });

  test('actual scoped factory and resolver bypass the compatibility override', () async {
    final session = AccountSession(configuration: _config, id: 'fixture-epoch');
    final legacy = LabSubsonicApiClient('target')..setConfig(_config);
    final store = OfflineStoreRepository(executor: NativeDatabase.memory());
    await store.registerScope(session.scope, context: session.requestContext);
    final directory = await Directory.systemTemp.createTemp('native_attribution_');
    final assets = AudioAssetRepository(store: store,
        directoryResolver: () async => Directory('${directory.path}/audio'));
    // This calls the exact production account factory, not a test reimplementation.
    final scopedProvider = Provider<SubsonicApiClient>((ref) {
      final client = createAccountApiClient(ref, ref.read(accountSessionProvider)!);
      ref.onDispose(client.dispose);
      return client;
    });
    final container = ProviderContainer(overrides: [
      accountSessionProvider.overrideWithValue(session),
      audioPlayerApiClientProvider.overrideWithValue(legacy),
    ]);
    addTearDown(() async {
      container.dispose();
      legacy.dispose();
      session.revoke();
      await store.close();
      await directory.delete(recursive: true);
    });
    final compatibility = container.read(audioPlayerApiClientProvider);
    _expectRealAuthAndRoute(compatibility.getStreamUrl(_song.id), marked: true);
    final scoped = container.read(scopedProvider);
    expect(identical(scoped, compatibility), isFalse);
    expect(scoped is NativeLabScopedApiClient, patched);
    var scopedCalls = 0;
    final resolver = AudioSourceResolver(
      apiClient: compatibility,
      sourcePolicy: PlaybackSourcePolicy(assets: assets),
      offlineContextResolver: () => session.requestContext,
      canAttemptRemote: () => true,
      scopedApiClientResolver: (context) {
        expect(identical(context, session.requestContext), isTrue);
        scopedCalls++;
        return scoped;
      },
      mediaStreamStrategyResolver: MediaStreamStrategyResolver(),
      resolveArtworkUri: (_, {required size}) async => null,
      cacheSongForStreamFailureFallback: (_) async => throw StateError('No cache fallback allowed'),
      cachePlaybackEnabledResolver: () async => false,
    );
    final resolved = await resolver.resolve(_song, resolveStreamStrategy: false);
    expect(scopedCalls, 1);
    expect(resolved.sourceKind, ResolvedAudioSourceKind.network);
    expect(resolved.stream!.originalUrl, resolved.stream!.resolvedUrl);
    _expectRealAuthAndRoute(resolved.stream!.resolvedUrl, marked: patched);
    // Existing account-boundary guard still rejects an actual API operation
    // before any HTTP request is sent, in both baseline and decorated runs.
    container.read(accountBoundaryBusyProvider.notifier).state = true;
    await expectLater(scoped.probeServer(), throwsA(_failure(OfflineFailureKind.cancelled)));
    session.revoke();
    expect(() => scoped.getStreamUrl(_song.id), throwsA(_failure(OfflineFailureKind.cancelled)));
    await expectLater(resolver.resolve(_song, resolveStreamStrategy: false),
        throwsA(_failure(OfflineFailureKind.cancelled)));
  });

  test('decoration preserves original URL bytes and every query value', () {
    const original = 'http://127.0.0.1:31337/rest/stream?u=fixture%2Baccount&t=abc&s=def&v=1.16.1&c=emosonic&id=fixture-track-a&variant=flac-no-picture&format=flac&maxBitRate=320';
    final decorated = _scope().decorate(original, songId: _song.id);
    expect(decorated, '$original&nativeLabInstance=target');
    final after = Map<String, List<String>>.from(Uri.parse(decorated).queryParametersAll)
      ..remove('nativeLabInstance');
    expect(after, Uri.parse(original).queryParametersAll);
  });

  test('decoration rejects external origin wrong port route and unowned tracks', () {
    for (final value in [
      'https://example.com/rest/stream?id=fixture-track-a',
      'http://127.0.0.1:31338/rest/stream?id=fixture-track-a',
      'http://127.0.0.1:31337/rest/download?id=fixture-track-a',
      'http://127.0.0.1:31337/rest/stream?id=unowned',
      'http://127.0.0.1:31337/rest/stream?id=fixture-track-a&id=unowned',
      'http://127.0.0.1:31337/rest/stream?id=fixture-track-a&nativeLabInstance=authority',
      'http://someone@127.0.0.1:31337/rest/stream?id=fixture-track-a',
      'http://127.0.0.1:31337/rest/stream?id=fixture-track-a#fragment',
    ]) {
      expect(() => _scope().decorate(value, songId: _song.id), throwsStateError);
    }
    expect(() => _scope().decorate('http://127.0.0.1:31337/rest/stream?id=unowned',
        songId: 'unowned'), throwsStateError);
    expect(() => _scope(instance: 'unrecognized'), throwsStateError);
  });

  test('superclass rejects revoked signed out and unreadable account first', () {
    for (final config in [
      _config.copyWith(isSignedOut: true),
      _config.copyWith(credentialsUnreadable: true),
    ]) {
      final client = NativeLabScopedApiClient(attribution: _scope())..setConfig(config);
      addTearDown(client.dispose);
      expect(() => client.getStreamUrl(_song.id), throwsA(_failure(OfflineFailureKind.authentication)));
    }
    final session = AccountSession(configuration: _config, id: 'revoked-epoch');
    final client = NativeLabScopedApiClient(requestContext: session.requestContext,
        attribution: _scope())..setConfig(_config, context: session.requestContext);
    addTearDown(client.dispose);
    session.revoke();
    expect(() => client.getStreamUrl(_song.id), throwsA(_failure(OfflineFailureKind.cancelled)));
  });

  test('scoped subclass forwards stream options without changing authentication', () {
    final client = NativeLabScopedApiClient(attribution: _scope())..setConfig(_config);
    addTearDown(client.dispose);
    final url = client.getStreamUrl(_song.id, variant: 'flac-no-picture',
        format: 'flac', maxBitRate: 320);
    _expectRealAuthAndRoute(url, marked: true);
    final query = Uri.parse(url).queryParameters;
    expect(query['variant'], 'flac-no-picture');
    expect(query['format'], 'flac');
    expect(query['maxBitRate'], '320');
  });
}

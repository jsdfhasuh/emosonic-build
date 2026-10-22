// Applied only to an owned disposable native-lab checkout, never production.
// The superclass retains its immutable account binding, guards and HTTP stack.
import 'dart:convert';
import 'dart:io';

import 'package:emosonic/data/services/subsonic/subsonic_api_client.dart';

class NativeLabStreamAttribution {
  NativeLabStreamAttribution({
    required this.instance,
    required this.fixtureStreamUri,
    required Set<String> trackIds,
  }) : trackIds = Set<String>.unmodifiable(trackIds) {
    if (!const {'authority', 'target', 'follower'}.contains(instance) ||
        fixtureStreamUri.scheme != 'http' ||
        fixtureStreamUri.host != '127.0.0.1' ||
        !fixtureStreamUri.hasPort ||
        fixtureStreamUri.port <= 0 ||
        fixtureStreamUri.userInfo.isNotEmpty ||
        fixtureStreamUri.path != '/rest/stream' ||
        fixtureStreamUri.hasQuery ||
        fixtureStreamUri.hasFragment ||
        trackIds.isEmpty ||
        trackIds.length > 32 ||
        trackIds.any((id) => id.isEmpty || id.length > 200)) {
      throw StateError('Native lab stream attribution scope refused');
    }
  }

  factory NativeLabStreamAttribution.fromEnvironment() {
    if (!const bool.fromEnvironment('EMOSONIC_NATIVE_MAC_LAB') ||
        Platform.environment['EMOSONIC_NATIVE_LAB'] != '1') {
      throw StateError('Native lab stream attribution requires the lab target');
    }
    final raw = Platform.environment['EMOSONIC_NATIVE_LAB_STREAM_SCOPE_JSON'];
    if (raw == null || raw.length > 8192) {
      throw StateError('Native lab stream attribution manifest missing');
    }
    final value = jsonDecode(raw);
    if (value is! Map<String, dynamic> ||
        value.keys.toSet().difference({'streamUrl', 'trackIds'}).isNotEmpty ||
        value['streamUrl'] is! String ||
        value['trackIds'] is! List ||
        (value['trackIds'] as List).any((id) => id is! String)) {
      throw StateError('Native lab stream attribution manifest invalid');
    }
    final ids = (value['trackIds'] as List).cast<String>();
    if (ids.toSet().length != ids.length) {
      throw StateError('Native lab stream attribution tracks are ambiguous');
    }
    return NativeLabStreamAttribution(
      instance: Platform.environment['EMOSONIC_NATIVE_LAB_ID'] ?? '',
      fixtureStreamUri: Uri.parse(value['streamUrl'] as String),
      trackIds: ids.toSet(),
    );
  }

  final String instance;
  final Uri fixtureStreamUri;
  final Set<String> trackIds;

  String decorate(String original, {required String songId}) {
    final uri = Uri.parse(original);
    if (uri.scheme != fixtureStreamUri.scheme ||
        uri.host != fixtureStreamUri.host ||
        uri.port != fixtureStreamUri.port ||
        uri.path != fixtureStreamUri.path ||
        uri.userInfo.isNotEmpty ||
        uri.hasFragment ||
        !uri.hasQuery ||
        !trackIds.contains(songId) ||
        uri.queryParametersAll['id']?.length != 1 ||
        uri.queryParameters['id'] != songId ||
        uri.queryParametersAll.containsKey('nativeLabInstance')) {
      throw StateError('Native lab stream attribution URL refused');
    }
    // Append only: preserve every byte of the production URL, including token,
    // salt, parameter encoding/order, route, variant, format and maxBitRate.
    return '$original&nativeLabInstance=${Uri.encodeComponent(instance)}';
  }
}

class NativeLabScopedApiClient extends SubsonicApiClient {
  NativeLabScopedApiClient({
    super.dio,
    super.requestContext,
    super.onRequestOutcome,
    super.requestGuard,
    super.requestBudget,
    NativeLabStreamAttribution? attribution,
  }) : _attribution = attribution;

  final NativeLabStreamAttribution? _attribution;

  @override
  String getStreamUrl(
    String songId, {
    String? variant,
    String? format,
    int? maxBitRate,
  }) {
    // The real immutable account checks and authentication run first. A failed
    // account is never rescued by instrumentation or a compatibility fallback.
    final original = super.getStreamUrl(songId,
        variant: variant, format: format, maxBitRate: maxBitRate);
    final scope = _attribution ?? NativeLabStreamAttribution.fromEnvironment();
    return scope.decorate(original, songId: songId);
  }
}

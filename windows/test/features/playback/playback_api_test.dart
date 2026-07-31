import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/core/auth/session_store.dart';
import 'package:sakuraplayer_windows/core/storage/secure_store.dart';
import 'package:sakuraplayer_windows/features/playback/data/playback_api.dart';

void main() {
  test(
    'session request sends exact Windows payload and resolves capabilities',
    () async {
      final adapter = _PlaybackAdapter(
        _manifestJson('/api/v1/playback/streams/$_sessionId'),
      );
      final api = await _api(adapter);

      final manifest = await api.createSession(
        cacheJobId: _jobId,
        mediaId: _mediaId,
        mode: PlaybackMode.original,
      );

      expect(adapter.request.path, 'cache-jobs/$_jobId/playback-sessions');
      expect(adapter.request.data, <String, Object?>{
        'media_id': _mediaId,
        'mode': 'original',
        'platform': 'windows',
        'client_instance_id': _clientId,
      });
      expect(adapter.request.headers['Authorization'], 'Bearer access-token');
      expect(
        manifest.streamUri.toString(),
        'https://server.test/api/v1/playback/streams/$_sessionId',
      );
      expect(manifest.mediaQueue.single.media.id, _mediaId);
    },
  );

  test('manifest rejects wrong UA and cross-origin capability URLs', () {
    expect(
      () => PlaybackManifestDto.fromJson(
        _manifestJson('/api/v1/playback/streams/$_sessionId')
          ..['required_user_agent'] = 'another-client',
        serverOrigin: Uri.parse('https://server.test'),
      ),
      throwsA(isA<ProtocolException>()),
    );
    expect(
      () => PlaybackManifestDto.fromJson(
        _manifestJson('https://other.test/stream'),
        serverOrigin: Uri.parse('https://server.test'),
      ),
      throwsA(isA<ProtocolException>()),
    );
    expect(
      () => PlaybackManifestDto.fromJson(
        _manifestJson('/api/v1/playback/streams/$_sessionId')
          ..remove('progress'),
        serverOrigin: Uri.parse('https://server.test'),
      ),
      throwsA(isA<ProtocolException>()),
    );
  });
}

Future<PlaybackApi> _api(_PlaybackAdapter adapter) async {
  final session = SessionStore(SecureStore(MemorySecureKeyValueStore()));
  await session.setTokens(
    TokenPair(
      accessToken: 'access-token',
      refreshToken: 'refresh-token',
      accessExpiresAt: DateTime.utc(2026, 8, 1),
      refreshExpiresAt: DateTime.utc(2026, 9, 1),
    ),
  );
  final dio = Dio(BaseOptions(baseUrl: 'https://server.test/api/v1/'))
    ..httpClientAdapter = adapter;
  return PlaybackApi(
    client: ApiClient(dio: dio, sessionStore: session),
    serverOrigin: Uri.parse('https://server.test'),
    clientInstanceId: () async => _clientId,
  );
}

Map<String, Object?> _manifestJson(String streamUrl) => <String, Object?>{
  'session_id': _sessionId,
  'cache_job_id': _jobId,
  'mode': 'original',
  'platform': 'windows',
  'stream_url': streamUrl,
  'expires_at': '2026-08-01T00:00:00Z',
  'subtitle_cache_expires_at': '2026-08-01T00:00:00Z',
  'required_user_agent': windowsPlaybackUserAgent,
  'embedded_tracks_source': 'client_player',
  'media_queue': <Object?>[
    <String, Object?>{
      'session_id': _sessionId,
      'media': <String, Object?>{
        'id': _mediaId,
        'candidate_id': _candidateId,
        'name': 'movie.mp4',
        'size_bytes': 1024,
        'duration_seconds': 60,
        'sequence_no': 0,
        'is_valid': true,
      },
      'stream_url': streamUrl,
    },
  ],
  'subtitles': <Object?>[],
  'progress': <String, Object?>{
    'position_seconds': 5,
    'duration_seconds': 60,
    'completed': false,
    'version': 1,
  },
};

class _PlaybackAdapter implements HttpClientAdapter {
  _PlaybackAdapter(this.response);

  final Map<String, Object?> response;
  late RequestOptions request;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    request = options;
    return ResponseBody.fromString(
      jsonEncode(response),
      201,
      headers: <String, List<String>>{
        Headers.contentTypeHeader: <String>['application/json'],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

const _jobId = '00000000-0000-4000-8000-000000000001';
const _mediaId = '00000000-0000-4000-8000-000000000002';
const _candidateId = '00000000-0000-4000-8000-000000000003';
const _sessionId = '00000000-0000-4000-8000-000000000004';
const _clientId = '00000000-0000-4000-8000-000000000005';

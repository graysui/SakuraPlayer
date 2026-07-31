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

  test('manifest rejects duplicate or out-of-queue subtitle grants', () {
    final subtitle = <String, Object?>{
      'id': _subtitleId,
      'media_id': _mediaId,
      'name': 'movie.zh.srt',
      'format': 'srt',
      'language': 'zh',
      'selected_by_default': true,
    };
    for (final subtitles in <List<Object?>>[
      <Object?>[subtitle, Map<String, Object?>.from(subtitle)],
      <Object?>[
        <String, Object?>{
          ...subtitle,
          'media_id': '00000000-0000-4000-8000-000000000099',
        },
      ],
    ]) {
      expect(
        () => PlaybackManifestDto.fromJson(
          _manifestJson('/api/v1/playback/streams/$_sessionId')
            ..['subtitles'] = subtitles,
          serverOrigin: Uri.parse('https://server.test'),
        ),
        throwsA(isA<ProtocolException>()),
      );
    }
  });

  test('progress responses require positive versions and known durations', () {
    for (final progress in <Map<String, Object?>>[
      <String, Object?>{
        'position_seconds': 5,
        'duration_seconds': 60,
        'completed': false,
        'version': 0,
      },
      <String, Object?>{
        'position_seconds': 0,
        'duration_seconds': 0,
        'completed': false,
        'version': 1,
      },
    ]) {
      expect(
        () => PlaybackProgressDto.fromJson(progress),
        throwsA(isA<ProtocolException>()),
      );
    }
  });

  test(
    'subtitle, progress and heartbeat use exact authenticated APIs',
    () async {
      final adapter = _RoutingAdapter();
      final api = await _apiForAdapter(adapter);

      final bytes = await api.downloadSubtitle(
        playbackSessionId: _sessionId,
        subtitleId: _subtitleId,
      );
      final progress = await api.updateProgress(
        movieId: _movieId,
        positionSeconds: 12.5,
        durationSeconds: null,
        version: 0,
      );
      final heartbeat = await api.heartbeat(
        playbackSessionId: _sessionId,
        positionSeconds: 15,
        durationSeconds: 60,
        version: progress.version,
        playing: false,
      );

      expect(bytes, utf8.encode('subtitle'));
      expect(progress.version, 1);
      expect(heartbeat.leaseExpiresAt, isNull);
      expect(heartbeat.progress!.version, 2);
      expect(adapter.requests.map((request) => request.path), <String>[
        'playback/sessions/$_sessionId/subtitles/$_subtitleId',
        'movies/$_movieId/progress',
        'playback/sessions/$_sessionId/heartbeat',
      ]);
      expect(adapter.requests[1].data, <String, Object?>{
        'position_seconds': 12.5,
        'duration_seconds': null,
        'version': 0,
      });
      expect(adapter.requests[2].data, <String, Object?>{
        'client_instance_id': _clientId,
        'progress': <String, Object?>{
          'position_seconds': 15.0,
          'duration_seconds': 60.0,
          'version': 1,
        },
        'playing': false,
      });
      expect(
        adapter.requests.every(
          (request) =>
              request.headers['Authorization'] == 'Bearer access-token',
        ),
        isTrue,
      );
    },
  );
}

Future<PlaybackApi> _api(_PlaybackAdapter adapter) async {
  return _apiForAdapter(adapter);
}

Future<PlaybackApi> _apiForAdapter(HttpClientAdapter adapter) async {
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

class _RoutingAdapter implements HttpClientAdapter {
  final List<RequestOptions> requests = <RequestOptions>[];

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options);
    if (options.path.endsWith('/subtitles/$_subtitleId')) {
      return ResponseBody.fromBytes(utf8.encode('subtitle'), 200);
    }
    if (options.path.endsWith('/progress')) {
      return _jsonResponse(<String, Object?>{
        'position_seconds': 12.5,
        'duration_seconds': null,
        'completed': false,
        'version': 1,
      });
    }
    return _jsonResponse(<String, Object?>{
      'lease_expires_at': null,
      'progress': <String, Object?>{
        'position_seconds': 15,
        'duration_seconds': 60,
        'completed': false,
        'version': 2,
      },
    });
  }

  ResponseBody _jsonResponse(Map<String, Object?> body) =>
      ResponseBody.fromString(
        jsonEncode(body),
        200,
        headers: <String, List<String>>{
          Headers.contentTypeHeader: <String>['application/json'],
        },
      );

  @override
  void close({bool force = false}) {}
}

const _jobId = '00000000-0000-4000-8000-000000000001';
const _mediaId = '00000000-0000-4000-8000-000000000002';
const _candidateId = '00000000-0000-4000-8000-000000000003';
const _sessionId = '00000000-0000-4000-8000-000000000004';
const _clientId = '00000000-0000-4000-8000-000000000005';
const _subtitleId = '00000000-0000-4000-8000-000000000006';
const _movieId = '00000000-0000-4000-8000-000000000007';

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/features/playback/data/playback_api.dart';
import 'package:sakuraplayer_windows/features/playback/presentation/playback_engine.dart';
import 'package:sakuraplayer_windows/features/playback/presentation/player_controller.dart';
import 'package:sakuraplayer_windows/features/playback/presentation/progress_controller.dart';
import 'package:sakuraplayer_windows/features/playback/presentation/track_controller.dart';

void main() {
  test(
    'opens original by default and every mode switch creates a session',
    () async {
      final gateway = _Gateway();
      final engine = _Engine();
      final progressGateway = _ProgressGateway();
      final controller = PlayerController(
        gateway: gateway,
        engine: engine,
        progress: ProgressController(
          gateway: progressGateway,
          movieId: _movieId,
          tickerFactory: (_, _) => const _NoopTicker(),
        ),
      );
      addTearDown(controller.dispose);

      await controller.initialize(cacheJobId: _jobId, mediaId: _mediaId);
      await controller.switchMode(PlaybackMode.compatibility);
      await controller.switchMode(PlaybackMode.original);

      expect(gateway.modes, [
        PlaybackMode.original,
        PlaybackMode.compatibility,
        PlaybackMode.original,
      ]);
      expect(engine.opened.length, 3);
      expect(progressGateway.endedSessions, <String>[
        '00000000-0000-4000-8000-000000000100',
        '00000000-0000-4000-8000-000000000101',
      ]);
      expect(controller.status, PlayerLoadStatus.ready);
    },
  );

  test(
    'only original unavailable automatically falls back to compatibility',
    () async {
      final gateway = _Gateway(
        errors: [
          const ApiException(
            code: 'cloud115_original_unavailable',
            message: 'unavailable',
          ),
        ],
      );
      final controller = PlayerController(gateway: gateway, engine: _Engine());
      addTearDown(controller.dispose);

      await controller.initialize(cacheJobId: _jobId, mediaId: _mediaId);

      expect(gateway.modes, [
        PlaybackMode.original,
        PlaybackMode.compatibility,
      ]);
      expect(controller.mode, PlaybackMode.compatibility);
      expect(controller.status, PlayerLoadStatus.ready);
    },
  );

  test(
    'expired manifest engine errors re-sign the same mode only once',
    () async {
      final gateway = _Gateway(expiresAt: DateTime.utc(2026, 7, 31, 10));
      final engine = _Engine();
      final controller = PlayerController(
        gateway: gateway,
        engine: engine,
        now: () => DateTime.utc(2026, 7, 31, 11),
      );
      addTearDown(controller.dispose);
      await controller.initialize(cacheJobId: _jobId, mediaId: _mediaId);

      engine.errors.add('HTTP 403');
      await Future<void>.delayed(Duration.zero);
      await Future<void>.delayed(Duration.zero);
      engine.errors.add('HTTP 403');
      await Future<void>.delayed(Duration.zero);

      expect(gateway.modes, [PlaybackMode.original, PlaybackMode.original]);
      expect(controller.status, PlayerLoadStatus.failed);
    },
  );

  test('non-expired engine error becomes visible without re-signing', () async {
    final gateway = _Gateway(expiresAt: DateTime.utc(2026, 8, 1));
    final engine = _Engine();
    final controller = PlayerController(
      gateway: gateway,
      engine: engine,
      now: () => DateTime.utc(2026, 7, 31, 11),
    );
    addTearDown(controller.dispose);
    await controller.initialize(cacheJobId: _jobId, mediaId: _mediaId);

    engine.errors.add('decoder failed');
    await Future<void>.delayed(Duration.zero);

    expect(gateway.modes, [PlaybackMode.original]);
    expect(controller.status, PlayerLoadStatus.failed);
    expect(controller.errorCode, 'player_playback_failed');
  });

  test('all seek entry points use the injected engine seek', () async {
    final engine = _Engine();
    final controller = PlayerController(gateway: _Gateway(), engine: engine);
    addTearDown(controller.dispose);
    await controller.initialize(cacheJobId: _jobId, mediaId: _mediaId);
    engine.positions.add(const Duration(seconds: 20));
    await Future<void>.delayed(Duration.zero);

    await controller.seekBy(const Duration(seconds: 10));
    await controller.seek(const Duration(seconds: 45));

    expect(engine.seeks, [
      const Duration(seconds: 30),
      const Duration(seconds: 45),
    ]);
  });

  test('media_kit playlist applies only the fixed UA to every item', () {
    final manifest = _manifest(
      PlaybackMode.original,
      DateTime.utc(2026, 8, 1),
      0,
    );

    final playlist = buildMediaKitPlaylist(manifest, _mediaId);
    final headers = playlist.medias.single.httpHeaders;

    expect(playlist.index, 0);
    expect(playlist.medias, hasLength(1));
    expect(headers, <String, String>{'User-Agent': windowsPlaybackUserAgent});
    expect(headers!.containsKey('Authorization'), isFalse);
  });
}

class _Gateway implements PlaybackGateway {
  _Gateway({this.errors = const [], DateTime? expiresAt})
    : expiresAt = expiresAt ?? DateTime.utc(2026, 8, 1);

  final List<ApiException> errors;
  final DateTime expiresAt;
  final List<PlaybackMode> modes = [];

  @override
  Future<PlaybackManifestDto> createSession({
    required String cacheJobId,
    required String mediaId,
    required PlaybackMode mode,
  }) async {
    modes.add(mode);
    final index = modes.length - 1;
    if (index < errors.length) throw errors[index];
    return _manifest(mode, expiresAt, index);
  }
}

class _Engine implements PlaybackEngine {
  final playing = StreamController<bool>.broadcast();
  final completed = StreamController<bool>.broadcast();
  final buffering = StreamController<bool>.broadcast();
  final positions = StreamController<Duration>.broadcast();
  final durations = StreamController<Duration>.broadcast();
  final errors = StreamController<String>.broadcast();
  final List<PlaybackManifestDto> opened = [];
  final List<Duration> seeks = [];

  @override
  Stream<bool> get playingStream => playing.stream;
  @override
  Stream<bool> get completedStream => completed.stream;
  @override
  Stream<bool> get bufferingStream => buffering.stream;
  @override
  Stream<Duration> get positionStream => positions.stream;
  @override
  Stream<Duration> get durationStream => durations.stream;
  @override
  Stream<String> get errorStream => errors.stream;
  @override
  Stream<EmbeddedTrackCatalog> get trackCatalogStream =>
      const Stream<EmbeddedTrackCatalog>.empty();
  @override
  Stream<EmbeddedTrackSelection> get trackSelectionStream =>
      const Stream<EmbeddedTrackSelection>.empty();
  @override
  Widget buildVideoSurface() => const ColoredBox(color: Colors.black);
  @override
  Future<void> open(PlaybackManifestDto manifest, String mediaId) async {
    opened.add(manifest);
  }

  @override
  Future<void> play() async {}
  @override
  Future<void> pause() async {}
  @override
  Future<void> seek(Duration target) async => seeks.add(target);
  @override
  Future<void> setRate(double rate) async {}
  @override
  Future<void> selectAudioTrack(String id) async {}
  @override
  Future<void> selectEmbeddedSubtitleTrack(String? id) async {}
  @override
  Future<void> setExternalSubtitle(
    Uri uri, {
    required String title,
    required String? language,
  }) async {}
  @override
  Future<void> toggleFullscreen() async {}
  @override
  Future<void> dispose() async {
    await Future.wait([
      playing.close(),
      completed.close(),
      buffering.close(),
      positions.close(),
      durations.close(),
      errors.close(),
    ]);
  }
}

class _ProgressGateway implements PlaybackProgressGateway {
  final List<String> endedSessions = <String>[];

  @override
  Future<PlaybackProgressDto> updateProgress({
    required String movieId,
    required double positionSeconds,
    required double? durationSeconds,
    required int version,
  }) async => PlaybackProgressDto(
    positionSeconds: positionSeconds,
    durationSeconds: durationSeconds,
    completed: false,
    version: version + 1,
  );

  @override
  Future<PlaybackHeartbeatDto> heartbeat({
    required String playbackSessionId,
    required double positionSeconds,
    required double? durationSeconds,
    required int version,
    required bool playing,
  }) async {
    if (!playing) endedSessions.add(playbackSessionId);
    return PlaybackHeartbeatDto(
      leaseExpiresAt: playing ? DateTime.utc(2026, 8, 1) : null,
      progress: PlaybackProgressDto(
        positionSeconds: positionSeconds,
        durationSeconds: durationSeconds,
        completed: false,
        version: version + 1,
      ),
    );
  }
}

class _NoopTicker implements ProgressTicker {
  const _NoopTicker();

  @override
  void cancel() {}
}

PlaybackManifestDto _manifest(
  PlaybackMode mode,
  DateTime expiresAt,
  int index,
) {
  final session =
      '00000000-0000-4000-8000-${(100 + index).toString().padLeft(12, '0')}';
  return PlaybackManifestDto(
    sessionId: session,
    cacheJobId: _jobId,
    mode: mode,
    streamUri: Uri.parse(
      'https://server.test/api/v1/playback/streams/$session',
    ),
    expiresAt: expiresAt,
    subtitleCacheExpiresAt: expiresAt,
    mediaQueue: [
      PlaybackQueueItemDto(
        sessionId: session,
        media: const RemoteMediaDto(
          id: _mediaId,
          candidateId: _candidateId,
          name: 'movie.mp4',
          sizeBytes: 100,
          durationSeconds: 60,
          sequenceNo: 1,
          isValid: true,
        ),
        streamUri: Uri.parse(
          'https://server.test/api/v1/playback/streams/$session',
        ),
      ),
    ],
    subtitles: const [],
    progress: null,
  );
}

const _jobId = '00000000-0000-4000-8000-000000000001';
const _mediaId = '00000000-0000-4000-8000-000000000002';
const _candidateId = '00000000-0000-4000-8000-000000000003';
const _movieId = '00000000-0000-4000-8000-000000000004';

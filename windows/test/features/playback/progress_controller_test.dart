import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/features/playback/data/playback_api.dart';
import 'package:sakuraplayer_windows/features/playback/presentation/progress_controller.dart';

void main() {
  test('live progress ignores out-of-order lower versions', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);
    final notifier = container.read(livePlaybackProgressProvider.notifier);

    notifier.update(
      _movieId,
      const PlaybackProgressDto(
        positionSeconds: 50,
        durationSeconds: 100,
        completed: false,
        version: 8,
      ),
    );
    notifier.update(
      _movieId,
      const PlaybackProgressDto(
        positionSeconds: 40,
        durationSeconds: 100,
        completed: false,
        version: 7,
      ),
    );

    expect(container.read(livePlaybackProgressProvider)[_movieId]!.version, 8);
  });

  test(
    'incomplete manifest progress resumes through the injected seek',
    () async {
      final ticker = _TickerFactory();
      final gateway = _ProgressGateway();
      final controller = ProgressController(
        gateway: gateway,
        movieId: _movieId,
        tickerFactory: ticker.call,
      );
      addTearDown(controller.dispose);
      final seeks = <Duration>[];

      controller.attachManifest(_manifest(position: 30, version: 3));
      await controller.resume((target) async => seeks.add(target));

      expect(seeks, <Duration>[const Duration(seconds: 30)]);
      expect(ticker.duration, playbackHeartbeatInterval);
    },
  );

  test(
    'periodic heartbeat sends current position and advances version',
    () async {
      final ticker = _TickerFactory();
      final gateway = _ProgressGateway();
      final published = <PlaybackProgressDto>[];
      final controller = ProgressController(
        gateway: gateway,
        movieId: _movieId,
        tickerFactory: ticker.call,
        onProgress: published.add,
      );
      addTearDown(controller.dispose);
      controller.attachManifest(_manifest(position: 5, version: 3));
      controller.updatePlayback(
        position: const Duration(seconds: 45),
        duration: const Duration(seconds: 100),
      );

      ticker.fire();
      await Future<void>.delayed(Duration.zero);
      await Future<void>.delayed(Duration.zero);

      expect(gateway.heartbeats.single.positionSeconds, 45);
      expect(gateway.heartbeats.single.durationSeconds, 100);
      expect(gateway.heartbeats.single.version, 3);
      expect(gateway.heartbeats.single.playing, isTrue);
      expect(controller.authoritativeProgress!.version, 4);
      expect(published.last.version, 4);
    },
  );

  test(
    'pause adopts a conflict version without replaying the old write',
    () async {
      final authoritative = <String, Object?>{
        'position_seconds': 50,
        'duration_seconds': 100,
        'completed': false,
        'version': 8,
      };
      final gateway = _ProgressGateway(
        progressError: ApiException(
          code: 'progress_version_conflict',
          message: 'conflict',
          statusCode: 409,
          details: <String, Object?>{'progress': authoritative},
        ),
      );
      final controller = ProgressController(
        gateway: gateway,
        movieId: _movieId,
        tickerFactory: _TickerFactory().call,
      );
      addTearDown(controller.dispose);
      controller.attachManifest(_manifest(position: 5, version: 3));
      controller.updatePlayback(
        position: const Duration(seconds: 40),
        duration: const Duration(seconds: 100),
      );

      await controller.flushPaused();

      expect(gateway.progressUpdates, hasLength(1));
      expect(controller.authoritativeProgress!.version, 8);
      expect(controller.errorCode, isNull);
    },
  );

  test(
    'completion flushes playing false and publishes server completion',
    () async {
      final ticker = _TickerFactory();
      final gateway = _ProgressGateway(completeHeartbeat: true);
      final controller = ProgressController(
        gateway: gateway,
        movieId: _movieId,
        tickerFactory: ticker.call,
      );
      addTearDown(controller.dispose);
      controller.attachManifest(_manifest(position: 94.99, version: 3));
      controller.updatePlayback(
        position: const Duration(seconds: 95),
        duration: const Duration(seconds: 100),
      );

      await controller.finish();

      expect(gateway.heartbeats.single.playing, isFalse);
      expect(gateway.heartbeats.single.positionSeconds, 95);
      expect(controller.authoritativeProgress!.completed, isTrue);
      expect(controller.authoritativeProgress!.positionSeconds, 0);
      expect(ticker.cancelled, isTrue);
    },
  );
}

class _ProgressGateway implements PlaybackProgressGateway {
  _ProgressGateway({this.progressError, this.completeHeartbeat = false});

  final ApiException? progressError;
  final bool completeHeartbeat;
  final List<_ProgressRequest> progressUpdates = <_ProgressRequest>[];
  final List<_HeartbeatRequest> heartbeats = <_HeartbeatRequest>[];

  @override
  Future<PlaybackProgressDto> updateProgress({
    required String movieId,
    required double positionSeconds,
    required double? durationSeconds,
    required int version,
  }) async {
    progressUpdates.add(
      _ProgressRequest(positionSeconds, durationSeconds, version),
    );
    final error = progressError;
    if (error != null) throw error;
    return PlaybackProgressDto(
      positionSeconds: positionSeconds,
      durationSeconds: durationSeconds,
      completed: false,
      version: version + 1,
    );
  }

  @override
  Future<PlaybackHeartbeatDto> heartbeat({
    required String playbackSessionId,
    required double positionSeconds,
    required double? durationSeconds,
    required int version,
    required bool playing,
  }) async {
    heartbeats.add(
      _HeartbeatRequest(positionSeconds, durationSeconds, version, playing),
    );
    return PlaybackHeartbeatDto(
      leaseExpiresAt: playing ? DateTime.utc(2026, 8, 1, 10, 1, 30) : null,
      progress: PlaybackProgressDto(
        positionSeconds: completeHeartbeat ? 0 : positionSeconds,
        durationSeconds: durationSeconds,
        completed: completeHeartbeat,
        version: version + 1,
      ),
    );
  }
}

class _TickerFactory {
  Duration? duration;
  VoidCallback? callback;
  bool cancelled = false;

  ProgressTicker call(Duration interval, VoidCallback tick) {
    duration = interval;
    callback = tick;
    return _FakeTicker(() => cancelled = true);
  }

  void fire() => callback?.call();
}

class _FakeTicker implements ProgressTicker {
  _FakeTicker(this._cancel);

  final VoidCallback _cancel;

  @override
  void cancel() => _cancel();
}

class _ProgressRequest {
  const _ProgressRequest(
    this.positionSeconds,
    this.durationSeconds,
    this.version,
  );

  final double positionSeconds;
  final double? durationSeconds;
  final int version;
}

class _HeartbeatRequest extends _ProgressRequest {
  const _HeartbeatRequest(
    super.positionSeconds,
    super.durationSeconds,
    super.version,
    this.playing,
  );

  final bool playing;
}

PlaybackManifestDto _manifest({
  required double position,
  required int version,
}) => PlaybackManifestDto(
  sessionId: _sessionId,
  cacheJobId: _jobId,
  mode: PlaybackMode.original,
  streamUri: Uri.parse('https://server.test/stream'),
  expiresAt: DateTime.utc(2026, 8, 1, 12),
  subtitleCacheExpiresAt: DateTime.utc(2026, 8, 1, 12),
  mediaQueue: <PlaybackQueueItemDto>[
    PlaybackQueueItemDto(
      sessionId: _sessionId,
      media: const RemoteMediaDto(
        id: _mediaId,
        candidateId: _candidateId,
        name: 'movie.mkv',
        sizeBytes: 100,
        durationSeconds: 100,
        sequenceNo: 0,
        isValid: true,
      ),
      streamUri: Uri.parse('https://server.test/stream'),
    ),
  ],
  subtitles: const <SubtitleOptionDto>[],
  progress: PlaybackProgressDto(
    positionSeconds: position,
    durationSeconds: 100,
    completed: false,
    version: version,
  ),
);

const _jobId = '00000000-0000-4000-8000-000000000001';
const _mediaId = '00000000-0000-4000-8000-000000000002';
const _candidateId = '00000000-0000-4000-8000-000000000003';
const _sessionId = '00000000-0000-4000-8000-000000000004';
const _movieId = '00000000-0000-4000-8000-000000000005';

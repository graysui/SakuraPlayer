import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/features/playback/data/playback_api.dart';

const playbackHeartbeatInterval = Duration(seconds: 15);

@immutable
class LivePlaybackProgress {
  const LivePlaybackProgress({
    required this.positionSeconds,
    required this.durationSeconds,
    required this.completed,
    required this.version,
  });

  factory LivePlaybackProgress.fromDto(PlaybackProgressDto value) =>
      LivePlaybackProgress(
        positionSeconds: value.positionSeconds,
        durationSeconds: value.durationSeconds,
        completed: value.completed,
        version: value.version,
      );

  final double positionSeconds;
  final double? durationSeconds;
  final bool completed;
  final int version;

  double? get fraction {
    final duration = durationSeconds;
    if (completed || duration == null) return null;
    return (positionSeconds / duration).clamp(0, 1).toDouble();
  }
}

class LivePlaybackProgressNotifier
    extends Notifier<Map<String, LivePlaybackProgress>> {
  @override
  Map<String, LivePlaybackProgress> build() =>
      const <String, LivePlaybackProgress>{};

  void update(String movieId, PlaybackProgressDto progress) {
    final current = state[movieId];
    if (current != null && progress.version <= current.version) return;
    state = Map<String, LivePlaybackProgress>.unmodifiable(
      <String, LivePlaybackProgress>{
        ...state,
        movieId: LivePlaybackProgress.fromDto(progress),
      },
    );
  }

  void clear() => state = const <String, LivePlaybackProgress>{};
}

LivePlaybackProgress? freshestLivePlaybackProgress(
  LivePlaybackProgress? live,
  int? persistedVersion,
) {
  if (live == null) return null;
  if (persistedVersion != null && persistedVersion > live.version) return null;
  return live;
}

final livePlaybackProgressProvider = NotifierProvider<
  LivePlaybackProgressNotifier,
  Map<String, LivePlaybackProgress>
>(LivePlaybackProgressNotifier.new);

abstract interface class ProgressTicker {
  void cancel();
}

typedef ProgressTickerFactory =
    ProgressTicker Function(Duration interval, VoidCallback tick);

class ProgressController extends ChangeNotifier {
  ProgressController({
    required PlaybackProgressGateway gateway,
    required String? movieId,
    ProgressTickerFactory? tickerFactory,
    ValueChanged<PlaybackProgressDto>? onProgress,
  }) : _gateway = gateway,
       _movieId = movieId,
       _tickerFactory = tickerFactory ?? _createTimerTicker,
       _onProgress = onProgress;

  final PlaybackProgressGateway _gateway;
  final String? _movieId;
  final ProgressTickerFactory _tickerFactory;
  final ValueChanged<PlaybackProgressDto>? _onProgress;

  PlaybackManifestDto? _manifest;
  ProgressTicker? _ticker;
  Future<void> _tail = Future<void>.value();
  Duration _position = Duration.zero;
  Duration _duration = Duration.zero;
  int _expectedVersion = 0;
  int _generation = 0;
  bool _ended = false;
  bool _disposed = false;

  PlaybackProgressDto? authoritativeProgress;
  String? errorCode;

  void attachManifest(PlaybackManifestDto manifest) {
    if (_disposed) return;
    _generation++;
    _manifest = manifest;
    _ended = false;
    errorCode = null;
    authoritativeProgress = manifest.progress;
    _expectedVersion = manifest.progress?.version ?? 0;
    _position = _seconds(manifest.progress?.positionSeconds ?? 0);
    _duration = _seconds(manifest.progress?.durationSeconds ?? 0);
    _ticker?.cancel();
    _ticker = _tickerFactory(
      playbackHeartbeatInterval,
      () => unawaited(heartbeatNow()),
    );
    final progress = authoritativeProgress;
    if (progress != null) _onProgress?.call(progress);
    notifyListeners();
  }

  Future<void> resume(Future<void> Function(Duration target) seek) async {
    final progress = authoritativeProgress;
    if (_disposed ||
        progress == null ||
        progress.completed ||
        progress.positionSeconds <= 0) {
      return;
    }
    await seek(_seconds(progress.positionSeconds));
  }

  void updatePlayback({
    required Duration position,
    required Duration duration,
  }) {
    if (_disposed) return;
    _position = position < Duration.zero ? Duration.zero : position;
    _duration = duration < Duration.zero ? Duration.zero : duration;
  }

  Future<void> heartbeatNow() => _enqueue(_ProgressAction.heartbeat);

  Future<void> flushPaused() => _enqueue(_ProgressAction.pause);

  Future<void> finish() {
    if (_ended) return _tail;
    _ticker?.cancel();
    _ticker = null;
    return _enqueue(_ProgressAction.finish);
  }

  Future<void> close() {
    if (_ended || _manifest == null) return _tail;
    return finish();
  }

  Future<void> _enqueue(_ProgressAction action) {
    if (_disposed ||
        _manifest == null ||
        (_ended && action != _ProgressAction.finish)) {
      return Future<void>.value();
    }
    if (action == _ProgressAction.finish) _ended = true;
    final operation = _tail.then((_) => _send(action));
    _tail = operation;
    return operation;
  }

  Future<void> _send(_ProgressAction action) async {
    final manifest = _manifest;
    if (_disposed || manifest == null) return;
    final generation = _generation;
    final positionSeconds = _position.inMilliseconds / 1000;
    final durationSeconds =
        _duration > Duration.zero ? _duration.inMilliseconds / 1000 : null;
    try {
      final PlaybackProgressDto? progress;
      final movieId = _movieId;
      if (action == _ProgressAction.pause && movieId != null) {
        progress = await _gateway.updateProgress(
          movieId: movieId,
          positionSeconds: positionSeconds,
          durationSeconds: durationSeconds,
          version: _expectedVersion,
        );
      } else {
        final response = await _gateway.heartbeat(
          playbackSessionId: manifest.sessionId,
          positionSeconds: positionSeconds,
          durationSeconds: durationSeconds,
          version: _expectedVersion,
          playing: action != _ProgressAction.finish,
        );
        progress = response.progress;
        if (progress == null) {
          throw const ApiException(
            code: 'client_protocol_error',
            message: 'Heartbeat omitted authoritative progress.',
          );
        }
      }
      if (_isCurrent(generation)) _apply(progress);
    } on ApiException catch (error) {
      if (!_isCurrent(generation)) return;
      if (error.code == 'progress_version_conflict') {
        final authoritative = _progressFromConflict(error);
        if (authoritative != null) {
          _apply(authoritative);
          return;
        }
      }
      errorCode = error.code;
      notifyListeners();
    } on Object {
      if (_isCurrent(generation)) {
        errorCode = 'progress_sync_failed';
        notifyListeners();
      }
    }
  }

  PlaybackProgressDto? _progressFromConflict(ApiException error) {
    final raw = error.details?['progress'];
    if (raw == null) return null;
    if (raw is! Map) return null;
    try {
      return PlaybackProgressDto.fromJson(Map<String, Object?>.from(raw));
    } on Object {
      return null;
    }
  }

  void _apply(PlaybackProgressDto progress) {
    authoritativeProgress = progress;
    _expectedVersion = progress.version;
    errorCode = null;
    _onProgress?.call(progress);
    notifyListeners();
  }

  bool _isCurrent(int generation) => !_disposed && generation == _generation;

  @override
  void dispose() {
    if (_disposed) return;
    _disposed = true;
    _generation++;
    _ticker?.cancel();
    _ticker = null;
    super.dispose();
  }
}

enum _ProgressAction { heartbeat, pause, finish }

Duration _seconds(num value) => Duration(
  milliseconds: (value.toDouble() * Duration.millisecondsPerSecond).round(),
);

ProgressTicker _createTimerTicker(Duration interval, VoidCallback tick) =>
    _TimerProgressTicker(Timer.periodic(interval, (_) => tick()));

class _TimerProgressTicker implements ProgressTicker {
  const _TimerProgressTicker(this._timer);

  final Timer _timer;

  @override
  void cancel() => _timer.cancel();
}

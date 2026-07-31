import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/features/playback/data/playback_api.dart';
import 'package:sakuraplayer_windows/features/playback/presentation/playback_engine.dart';
import 'package:sakuraplayer_windows/features/playback/presentation/throttling_player.dart';

enum PlayerLoadStatus { idle, loading, ready, failed }

class PlayerController extends ChangeNotifier {
  PlayerController({
    required PlaybackGateway gateway,
    required this.engine,
    DateTime Function()? now,
  }) : _gateway = gateway,
       _now = now ?? (() => DateTime.now().toUtc()),
       _seeker = ThrottlingPlayer(engine.seek) {
    _subscriptions.addAll([
      engine.playingStream.listen((value) {
        if (_disposed) return;
        isPlaying = value;
        notifyListeners();
      }),
      engine.bufferingStream.listen((value) {
        if (_disposed) return;
        isBuffering = value;
        notifyListeners();
      }),
      engine.positionStream.listen((value) {
        if (_disposed) return;
        position = value;
        notifyListeners();
      }),
      engine.durationStream.listen((value) {
        if (_disposed) return;
        duration = value;
        notifyListeners();
      }),
      engine.errorStream.listen(
        (value) => unawaited(_handleEngineError(value)),
      ),
    ]);
  }

  final PlaybackGateway _gateway;
  final DateTime Function() _now;
  final ThrottlingPlayer _seeker;
  final List<StreamSubscription<Object?>> _subscriptions = [];
  final PlaybackEngine engine;

  PlayerLoadStatus status = PlayerLoadStatus.idle;
  PlaybackMode mode = PlaybackMode.original;
  PlaybackManifestDto? manifest;
  String? errorCode;
  bool isPlaying = false;
  bool isBuffering = false;
  Duration position = Duration.zero;
  Duration duration = Duration.zero;
  double rate = 1;
  String? _cacheJobId;
  String? _mediaId;
  int _generation = 0;
  bool _expiryRetryUsed = false;
  bool _disposed = false;

  Future<void> initialize({
    required String cacheJobId,
    required String mediaId,
  }) async {
    _cacheJobId = cacheJobId;
    _mediaId = mediaId;
    mode = PlaybackMode.original;
    _expiryRetryUsed = false;
    await _load(mode, allowOriginalFallback: true, newGeneration: true);
  }

  Future<void> switchMode(PlaybackMode next) async {
    if (_disposed || status == PlayerLoadStatus.loading || next == mode) return;
    _expiryRetryUsed = false;
    await _load(next, allowOriginalFallback: false, newGeneration: true);
  }

  Future<void> retry() async {
    if (_disposed || status == PlayerLoadStatus.loading) return;
    _expiryRetryUsed = false;
    await _load(mode, allowOriginalFallback: false, newGeneration: true);
  }

  Future<void> _load(
    PlaybackMode target, {
    required bool allowOriginalFallback,
    required bool newGeneration,
  }) async {
    final jobId = _cacheJobId;
    final mediaId = _mediaId;
    if (jobId == null || mediaId == null) return;
    final generation = newGeneration ? ++_generation : _generation;
    status = PlayerLoadStatus.loading;
    errorCode = null;
    notifyListeners();
    try {
      final result = await _gateway.createSession(
        cacheJobId: jobId,
        mediaId: mediaId,
        mode: target,
      );
      if (!_isCurrent(generation)) return;
      mode = result.mode;
      manifest = result;
      await engine.open(result, mediaId);
      if (!_isCurrent(generation)) return;
      status = PlayerLoadStatus.ready;
      notifyListeners();
    } on ApiException catch (error) {
      if (!_isCurrent(generation)) return;
      if (allowOriginalFallback &&
          target == PlaybackMode.original &&
          error.code == 'cloud115_original_unavailable') {
        await _load(
          PlaybackMode.compatibility,
          allowOriginalFallback: false,
          newGeneration: false,
        );
        return;
      }
      status = PlayerLoadStatus.failed;
      errorCode = error.code;
      notifyListeners();
    } on Object {
      if (!_isCurrent(generation)) return;
      status = PlayerLoadStatus.failed;
      errorCode = 'player_open_failed';
      notifyListeners();
    }
  }

  Future<void> _handleEngineError(String _) async {
    final current = manifest;
    if (_disposed || status != PlayerLoadStatus.ready || current == null) {
      return;
    }
    if (!_expiryRetryUsed && !_now().isBefore(current.expiresAt)) {
      _expiryRetryUsed = true;
      await _load(mode, allowOriginalFallback: false, newGeneration: false);
    } else if (!_disposed) {
      status = PlayerLoadStatus.failed;
      errorCode = 'player_playback_failed';
      notifyListeners();
    }
  }

  Future<void> togglePlayPause() => isPlaying ? engine.pause() : engine.play();

  Future<void> seek(Duration target) {
    final upper = duration;
    final bounded = upper > Duration.zero && target > upper ? upper : target;
    return _seeker.seek(bounded);
  }

  Future<void> seekBy(Duration delta) => seek(position + delta);

  Future<void> setRate(double value) async {
    if (!const <double>[0.5, 1, 1.25, 1.5, 2].contains(value)) return;
    await engine.setRate(value);
    rate = value;
    notifyListeners();
  }

  bool _isCurrent(int generation) => !_disposed && generation == _generation;

  @override
  void dispose() {
    if (_disposed) return;
    _disposed = true;
    _generation++;
    _seeker.dispose();
    for (final subscription in _subscriptions) {
      unawaited(subscription.cancel());
    }
    unawaited(engine.dispose());
    super.dispose();
  }
}

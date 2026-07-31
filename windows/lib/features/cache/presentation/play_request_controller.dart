import 'dart:async';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/core/events/snapshot_controller.dart';
import 'package:sakuraplayer_windows/features/cache/data/play_request_api.dart';

enum PlayRequestPhase {
  idle,
  submitting,
  waiting,
  queued,
  existing,
  ready,
  timedOut,
  cancelled,
  failed,
}

enum PlayRequestAction {
  openPlayer,
  openWait,
  showQueued,
  showExisting,
  showTimedOut,
  showError,
  ignored,
}

@immutable
class PlayRequestState {
  const PlayRequestState({
    required this.phase,
    required this.movieId,
    required this.sourceId,
    required this.job,
    required this.remainingSeconds,
    required this.errorCode,
    required this.navigationRevision,
  });

  const PlayRequestState.initial()
    : phase = PlayRequestPhase.idle,
      movieId = null,
      sourceId = null,
      job = null,
      remainingSeconds = 0,
      errorCode = null,
      navigationRevision = 0;

  final PlayRequestPhase phase;
  final String? movieId;
  final String? sourceId;
  final CacheJobDto? job;
  final int remainingSeconds;
  final String? errorCode;
  final int navigationRevision;

  PlayRequestState copyWith({
    PlayRequestPhase? phase,
    CacheJobDto? job,
    int? remainingSeconds,
    Object? errorCode = _absent,
    int? navigationRevision,
  }) => PlayRequestState(
    phase: phase ?? this.phase,
    movieId: movieId,
    sourceId: sourceId,
    job: job ?? this.job,
    remainingSeconds: remainingSeconds ?? this.remainingSeconds,
    errorCode:
        identical(errorCode, _absent) ? this.errorCode : errorCode as String?,
    navigationRevision: navigationRevision ?? this.navigationRevision,
  );
}

abstract interface class PlayRequestClock {
  DateTime wallNow();

  Duration monotonicNow();
}

class SystemPlayRequestClock implements PlayRequestClock {
  SystemPlayRequestClock() : _stopwatch = Stopwatch()..start();

  final Stopwatch _stopwatch;

  @override
  DateTime wallNow() => DateTime.now().toUtc();

  @override
  Duration monotonicNow() => _stopwatch.elapsed;
}

final playRequestClockProvider = Provider<PlayRequestClock>(
  (ref) => SystemPlayRequestClock(),
);

final playRequestControllerProvider =
    NotifierProvider<PlayRequestController, PlayRequestState>(
      PlayRequestController.new,
    );

class PlayRequestController extends Notifier<PlayRequestState> {
  Future<PlayRequestAction>? _inFlight;
  Duration? _monotonicDeadline;
  Timer? _timer;

  @override
  PlayRequestState build() {
    ref.listen<SnapshotState>(snapshotStateProvider, (_, next) {
      _applySnapshot(next);
    });
    ref.onDispose(_cancelTimer);
    return const PlayRequestState.initial();
  }

  Future<PlayRequestAction> submit({
    required String movieId,
    required String sourceId,
  }) {
    requireUuid(movieId, 'movieId');
    requireUuid(sourceId, 'sourceId');
    final active = _inFlight;
    if (active != null) {
      return Future<PlayRequestAction>.value(PlayRequestAction.ignored);
    }
    final operation = _submit(movieId: movieId, sourceId: sourceId);
    _inFlight = operation;
    unawaited(
      operation.then<void>(
        (_) => _clearInFlight(operation),
        onError: (Object _, StackTrace __) => _clearInFlight(operation),
      ),
    );
    return operation;
  }

  Future<PlayRequestAction> _submit({
    required String movieId,
    required String sourceId,
  }) async {
    _cancelTimer();
    _monotonicDeadline = null;
    state = PlayRequestState(
      phase: PlayRequestPhase.submitting,
      movieId: movieId,
      sourceId: sourceId,
      job: null,
      remainingSeconds: 0,
      errorCode: null,
      navigationRevision: 0,
    );
    try {
      final result = await ref
          .read(playRequestGatewayProvider)
          .request(
            movieId: movieId,
            sourceId: sourceId,
            idempotencyKey: _newIdempotencyKey(),
          );
      return _applyResult(result);
    } on ApiException catch (error) {
      state = state.copyWith(
        phase: PlayRequestPhase.failed,
        errorCode: error.code,
      );
      return PlayRequestAction.showError;
    }
  }

  PlayRequestAction _applyResult(PlayRequestResultDto result) {
    if (result.disposition == PlayDisposition.ready ||
        (result.disposition == PlayDisposition.reused &&
            result.cacheJob.status == 'ready')) {
      state = state.copyWith(
        phase: PlayRequestPhase.ready,
        job: result.cacheJob,
        errorCode: null,
        navigationRevision: state.navigationRevision + 1,
      );
      return PlayRequestAction.openPlayer;
    }
    if (result.disposition == PlayDisposition.started) {
      final clock = ref.read(playRequestClockProvider);
      var remaining = result.waitDeadline!.difference(clock.wallNow());
      if (remaining.isNegative) remaining = Duration.zero;
      if (remaining > const Duration(seconds: 60)) {
        remaining = const Duration(seconds: 60);
      }
      _monotonicDeadline = clock.monotonicNow() + remaining;
      state = state.copyWith(
        phase:
            remaining == Duration.zero
                ? PlayRequestPhase.timedOut
                : PlayRequestPhase.waiting,
        job: result.cacheJob,
        remainingSeconds: _ceilSeconds(remaining),
        errorCode: null,
      );
      if (remaining == Duration.zero) return PlayRequestAction.showTimedOut;
      _applySnapshot(ref.read(snapshotStateProvider));
      if (state.phase == PlayRequestPhase.waiting) {
        _timer = Timer.periodic(
          const Duration(seconds: 1),
          (_) => refreshTime(),
        );
        return PlayRequestAction.openWait;
      }
      return switch (state.phase) {
        PlayRequestPhase.ready => PlayRequestAction.openPlayer,
        PlayRequestPhase.existing => PlayRequestAction.showExisting,
        PlayRequestPhase.timedOut => PlayRequestAction.showTimedOut,
        _ => PlayRequestAction.showError,
      };
    }
    if (result.disposition == PlayDisposition.queued) {
      state = state.copyWith(
        phase: PlayRequestPhase.queued,
        job: result.cacheJob,
        errorCode: null,
      );
      return PlayRequestAction.showQueued;
    }
    state = state.copyWith(
      phase: PlayRequestPhase.existing,
      job: result.cacheJob,
      errorCode: null,
    );
    return PlayRequestAction.showExisting;
  }

  void refreshTime() {
    if (state.phase != PlayRequestPhase.waiting || _monotonicDeadline == null) {
      return;
    }
    final remaining =
        _monotonicDeadline! - ref.read(playRequestClockProvider).monotonicNow();
    if (remaining <= Duration.zero) {
      _cancelTimer();
      state = state.copyWith(
        phase: PlayRequestPhase.timedOut,
        remainingSeconds: 0,
      );
      return;
    }
    final seconds = _ceilSeconds(remaining);
    if (seconds != state.remainingSeconds) {
      state = state.copyWith(remainingSeconds: seconds);
    }
  }

  Future<bool> cancel({required bool confirmed}) async {
    final job = state.job;
    if (!confirmed || state.phase != PlayRequestPhase.waiting || job == null) {
      return false;
    }
    try {
      final cancelled = await ref
          .read(playRequestGatewayProvider)
          .cancel(job.id, confirmed: true);
      _cancelTimer();
      state = state.copyWith(
        phase: PlayRequestPhase.cancelled,
        job: cancelled,
        remainingSeconds: 0,
        errorCode: null,
      );
      return true;
    } on ApiException catch (error) {
      state = state.copyWith(errorCode: error.code);
      return false;
    }
  }

  void reset() {
    _cancelTimer();
    _monotonicDeadline = null;
    state = const PlayRequestState.initial();
  }

  void _applySnapshot(SnapshotState snapshot) {
    if (state.phase != PlayRequestPhase.waiting || state.job == null) return;
    final updated = snapshot.cacheJobs[state.job!.id];
    if (updated == null) return;
    if (updated.status == 'ready') {
      final clock = ref.read(playRequestClockProvider);
      final inTime =
          _monotonicDeadline != null &&
          clock.monotonicNow() < _monotonicDeadline!;
      if (!inTime) {
        refreshTime();
        return;
      }
      _cancelTimer();
      state = state.copyWith(
        phase: PlayRequestPhase.ready,
        job: updated,
        remainingSeconds: 0,
        errorCode: null,
        navigationRevision: state.navigationRevision + 1,
      );
      return;
    }
    if (updated.status == 'failed') {
      _cancelTimer();
      state = state.copyWith(
        phase: PlayRequestPhase.failed,
        job: updated,
        errorCode: updated.errorCode ?? 'cache_failed',
      );
      return;
    }
    if (updated.status == 'awaiting_selection') {
      _cancelTimer();
      state = state.copyWith(
        phase: PlayRequestPhase.existing,
        job: updated,
        remainingSeconds: 0,
      );
      return;
    }
    if (updated.status == 'cleaned' || updated.status == 'detached') {
      _cancelTimer();
      state = state.copyWith(
        phase: PlayRequestPhase.cancelled,
        job: updated,
        remainingSeconds: 0,
      );
      return;
    }
    state = state.copyWith(job: updated);
  }

  void _cancelTimer() {
    _timer?.cancel();
    _timer = null;
  }

  void _clearInFlight(Future<PlayRequestAction> operation) {
    if (identical(_inFlight, operation)) _inFlight = null;
  }
}

int _ceilSeconds(Duration value) =>
    (value.inMicroseconds / Duration.microsecondsPerSecond).ceil();

String _newIdempotencyKey() {
  final random = Random.secure();
  final values = List<int>.generate(16, (_) => random.nextInt(256));
  values[6] = (values[6] & 0x0f) | 0x40;
  values[8] = (values[8] & 0x3f) | 0x80;
  final hex =
      values.map((value) => value.toRadixString(16).padLeft(2, '0')).join();
  return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-'
      '${hex.substring(12, 16)}-${hex.substring(16, 20)}-${hex.substring(20)}';
}

const _absent = Object();

import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/core/events/snapshot_controller.dart';
import 'package:sakuraplayer_windows/features/cache/data/play_request_api.dart';
import 'package:sakuraplayer_windows/features/cache/presentation/cache_notifications.dart';
import 'package:sakuraplayer_windows/features/cache/presentation/play_request_controller.dart';

void main() {
  group('PlayRequestResultDto', () {
    test('parses all dispositions and enforces deadline relationships', () {
      for (final disposition in PlayDisposition.values) {
        final json = _resultJson(disposition);
        final result = PlayRequestResultDto.fromJson(json);
        expect(result.disposition, disposition);
        expect(result.cacheJob.id, jobId);
      }

      expect(
        () => PlayRequestResultDto.fromJson(
          _resultJson(PlayDisposition.started)..['wait_deadline'] = null,
        ),
        throwsA(isA<ProtocolException>()),
      );
      expect(
        () => PlayRequestResultDto.fromJson(
          _resultJson(PlayDisposition.queued)
            ..['wait_deadline'] = '2026-07-31T12:01:00Z',
        ),
        throwsA(isA<ProtocolException>()),
      );
      expect(
        () => PlayRequestResultDto.fromJson(
          _resultJson(PlayDisposition.ready)..['unexpected'] = true,
        ),
        throwsA(isA<ProtocolException>()),
      );
    });

    test('accepts omitted nullable cache job fields from play request', () {
      final json = _resultJson(PlayDisposition.started);
      final cacheJob = json['cache_job']! as Map<String, Object?>;
      cacheJob
        ..remove('error_code')
        ..remove('ready_at')
        ..remove('expires_at');

      final result = PlayRequestResultDto.fromJson(json);

      expect(result.cacheJob.errorCode, isNull);
      expect(result.cacheJob.readyAt, isNull);
      expect(result.cacheJob.expiresAt, isNull);
    });

    test('accepts omitted wait deadline for a ready reuse response', () {
      final json = _resultJson(PlayDisposition.ready)..remove('wait_deadline');

      final result = PlayRequestResultDto.fromJson(json);

      expect(result.disposition, PlayDisposition.ready);
      expect(result.waitDeadline, isNull);
      expect(result.cacheJob.status, 'ready');
    });

    test(
      'gateway sends only source_id with a safe idempotency header',
      () async {
        final client = _RecordingApiClient();
        final api = PlayRequestApi(client);

        await api.request(
          movieId: movieId,
          sourceId: sourceId,
          idempotencyKey: '12345678-1234-4123-8123-123456789abc',
        );

        expect(client.path, 'movies/$movieId/play-requests');
        expect(client.data, <String, Object?>{'source_id': sourceId});
        expect(client.headers, <String, Object?>{
          'Idempotency-Key': '12345678-1234-4123-8123-123456789abc',
        });
      },
    );
  });

  group('PlayRequestController', () {
    test(
      'ready plays, while queued and reused running never auto-play',
      () async {
        final gateway = _PlayGateway();
        final clock = _TestClock();
        final container = _container(gateway, clock);
        addTearDown(container.dispose);
        final controller = container.read(
          playRequestControllerProvider.notifier,
        );

        gateway.next = _result(PlayDisposition.ready, status: 'ready');
        expect(
          await controller.submit(movieId: movieId, sourceId: sourceId),
          PlayRequestAction.openPlayer,
        );

        controller.reset();
        gateway.next = _result(PlayDisposition.queued, status: 'queued');
        expect(
          await controller.submit(movieId: movieId, sourceId: sourceId),
          PlayRequestAction.showQueued,
        );

        controller.reset();
        gateway.next = _result(PlayDisposition.reused, status: 'offlining');
        expect(
          await controller.submit(movieId: movieId, sourceId: sourceId),
          PlayRequestAction.showExisting,
        );
        expect(gateway.keys.toSet().length, 3);
      },
    );

    test('started auto-plays at 59 seconds and only once', () async {
      final gateway = _PlayGateway(
        next: _result(PlayDisposition.started, status: 'submitting'),
      );
      final clock = _TestClock();
      final container = _container(gateway, clock);
      addTearDown(container.dispose);
      final controller = container.read(playRequestControllerProvider.notifier);

      expect(
        await controller.submit(movieId: movieId, sourceId: sourceId),
        PlayRequestAction.openWait,
      );
      clock.advance(const Duration(seconds: 59));
      container
          .read(snapshotStateProvider.notifier)
          .replace(_snapshot(_job('ready')));

      expect(
        container.read(playRequestControllerProvider).phase,
        PlayRequestPhase.ready,
      );
      expect(
        container.read(playRequestControllerProvider).navigationRevision,
        1,
      );
      container
          .read(snapshotStateProvider.notifier)
          .replace(_snapshot(_job('ready'), version: 2));
      expect(
        container.read(playRequestControllerProvider).navigationRevision,
        1,
      );
    });

    test('60 seconds times out and late ready never auto-plays', () async {
      final gateway = _PlayGateway(
        next: _result(PlayDisposition.started, status: 'submitting'),
      );
      final clock = _TestClock();
      final container = _container(gateway, clock);
      addTearDown(container.dispose);
      final controller = container.read(playRequestControllerProvider.notifier);

      await controller.submit(movieId: movieId, sourceId: sourceId);
      clock.advance(const Duration(seconds: 60));
      controller.refreshTime();
      expect(
        container.read(playRequestControllerProvider).phase,
        PlayRequestPhase.timedOut,
      );

      container
          .read(snapshotStateProvider.notifier)
          .replace(_snapshot(_job('ready')));
      final state = container.read(playRequestControllerProvider);
      expect(state.phase, PlayRequestPhase.timedOut);
      expect(state.navigationRevision, 0);
    });

    test(
      'handles zero and one second server deadlines deterministically',
      () async {
        final gateway = _PlayGateway(
          next: PlayRequestResultDto(
            disposition: PlayDisposition.started,
            waitDeadline: DateTime.utc(2026, 7, 31, 12),
            cacheJob: _job('submitting'),
          ),
        );
        final clock = _TestClock();
        final container = _container(gateway, clock);
        addTearDown(container.dispose);
        final controller = container.read(
          playRequestControllerProvider.notifier,
        );

        expect(
          await controller.submit(movieId: movieId, sourceId: sourceId),
          PlayRequestAction.showTimedOut,
        );
        expect(
          container.read(playRequestControllerProvider).remainingSeconds,
          0,
        );

        controller.reset();
        gateway.next = PlayRequestResultDto(
          disposition: PlayDisposition.started,
          waitDeadline: clock.wallNow().add(const Duration(seconds: 1)),
          cacheJob: _job('submitting'),
        );
        expect(
          await controller.submit(movieId: movieId, sourceId: sourceId),
          PlayRequestAction.openWait,
        );
        expect(
          container.read(playRequestControllerProvider).remainingSeconds,
          1,
        );
        clock.advance(const Duration(seconds: 1));
        controller.refreshTime();
        expect(
          container.read(playRequestControllerProvider).phase,
          PlayRequestPhase.timedOut,
        );
      },
    );

    test('awaiting selection exits blocking wait without auto-play', () async {
      final gateway = _PlayGateway(
        next: _result(PlayDisposition.started, status: 'submitting'),
      );
      final container = _container(gateway, _TestClock());
      addTearDown(container.dispose);
      final controller = container.read(playRequestControllerProvider.notifier);
      await controller.submit(movieId: movieId, sourceId: sourceId);

      container
          .read(snapshotStateProvider.notifier)
          .replace(_snapshot(_job('awaiting_selection')));

      final state = container.read(playRequestControllerProvider);
      expect(state.phase, PlayRequestPhase.existing);
      expect(state.navigationRevision, 0);
    });

    test(
      'deduplicates an in-flight click and reuses one idempotency key',
      () async {
        final completer = Completer<PlayRequestResultDto>();
        final gateway = _PlayGateway(pending: completer);
        final container = _container(gateway, _TestClock());
        addTearDown(container.dispose);
        final controller = container.read(
          playRequestControllerProvider.notifier,
        );

        final first = controller.submit(movieId: movieId, sourceId: sourceId);
        final second = controller.submit(movieId: movieId, sourceId: sourceId);
        expect(gateway.calls, 1);
        completer.complete(_result(PlayDisposition.queued, status: 'queued'));

        expect(await first, PlayRequestAction.showQueued);
        expect(await second, PlayRequestAction.ignored);
        expect(gateway.keys, hasLength(1));
        expect(gateway.keys.single.length, inInclusiveRange(16, 128));
      },
    );

    test('reconciles a ready snapshot that arrived before response', () async {
      final completer = Completer<PlayRequestResultDto>();
      final gateway = _PlayGateway(pending: completer);
      final container = _container(gateway, _TestClock());
      addTearDown(container.dispose);
      final controller = container.read(playRequestControllerProvider.notifier);

      final action = controller.submit(movieId: movieId, sourceId: sourceId);
      container
          .read(snapshotStateProvider.notifier)
          .replace(_snapshot(_job('ready')));
      completer.complete(
        _result(PlayDisposition.started, status: 'submitting'),
      );

      expect(await action, PlayRequestAction.openPlayer);
      expect(
        container.read(playRequestControllerProvider).phase,
        PlayRequestPhase.ready,
      );
      expect(
        container.read(playRequestControllerProvider).navigationRevision,
        1,
      );
    });

    test(
      'confirmed cancel succeeds, while API failure keeps waiting',
      () async {
        final gateway = _PlayGateway(
          next: _result(PlayDisposition.started, status: 'submitting'),
        );
        final container = _container(gateway, _TestClock());
        addTearDown(container.dispose);
        final controller = container.read(
          playRequestControllerProvider.notifier,
        );
        await controller.submit(movieId: movieId, sourceId: sourceId);

        gateway.cancelError = const ApiException(
          code: 'cache_active_lease',
          message: 'fixture',
        );
        expect(await controller.cancel(confirmed: true), isFalse);
        expect(
          container.read(playRequestControllerProvider).phase,
          PlayRequestPhase.waiting,
        );
        expect(
          container.read(playRequestControllerProvider).errorCode,
          'cache_active_lease',
        );

        gateway.cancelError = null;
        expect(await controller.cancel(confirmed: true), isTrue);
        expect(
          container.read(playRequestControllerProvider).phase,
          PlayRequestPhase.cancelled,
        );
        expect(gateway.cancelConfirmed, everyElement(isTrue));
      },
    );
  });

  group('Windows cache notifications', () {
    test('defines fixed copy for every supported notification type', () {
      final expected = <String, (String, String)>{
        'cache_started': ('缓存任务开始', '任务正在后台处理，不会自动播放'),
        'cache_ready': ('缓存已就绪', '可在缓存页查看并播放'),
        'cache_failed': ('缓存任务失败', '可在缓存页查看失败原因'),
        'credential_expired': ('115 凭据已失效', '请在设置中重新扫码'),
      };

      for (final entry in expected.entries) {
        final content = CacheNotificationContent.from(_notification(entry.key));
        expect(content.title, entry.value.$1);
        expect(content.body, entry.value.$2);
      }
    });

    test('uses fixed safe copy and opens only the cache route', () async {
      var opened = 0;
      final port = _ToastPort();
      final sink = WindowsCacheNotificationSink(
        port: port,
        onOpenCache: () => opened++,
      );
      final notification = _notification('cache_failed', errorCode: 'cache_x');

      expect(await sink.show(notification), isTrue);
      expect(port.title, '缓存任务失败');
      expect(port.body, contains('cache_x'));
      expect(port.body, isNot(contains('magnet')));
      expect(port.payload, notificationId);

      port.activate!('not-a-uuid');
      expect(opened, 0);
      port.activate!(notificationId);
      expect(opened, 1);
    });

    test(
      'returns false when platform initialization or display fails',
      () async {
        final port = _ToastPort()..failure = StateError('fixture');
        final sink = WindowsCacheNotificationSink(
          port: port,
          onOpenCache: () {},
        );
        expect(await sink.show(_notification('cache_ready')), isFalse);
      },
    );
  });
}

ProviderContainer _container(_PlayGateway gateway, _TestClock clock) =>
    ProviderContainer(
      overrides: [
        playRequestGatewayProvider.overrideWithValue(gateway),
        playRequestClockProvider.overrideWithValue(clock),
      ],
    );

Map<String, Object?> _resultJson(
  PlayDisposition disposition,
) => <String, Object?>{
  'disposition': disposition.name,
  'wait_deadline':
      disposition == PlayDisposition.started ? '2026-07-31T12:01:00Z' : null,
  'cache_job': _jobJson(
    disposition == PlayDisposition.ready
        ? 'ready'
        : disposition == PlayDisposition.started
        ? 'submitting'
        : disposition == PlayDisposition.queued
        ? 'queued'
        : 'offlining',
  ),
};

PlayRequestResultDto _result(
  PlayDisposition disposition, {
  required String status,
}) => PlayRequestResultDto(
  disposition: disposition,
  waitDeadline:
      disposition == PlayDisposition.started
          ? DateTime.utc(2026, 7, 31, 12, 1)
          : null,
  cacheJob: _job(status),
);

Map<String, Object?> _jobJson(String status) => <String, Object?>{
  'id': jobId,
  'movie_id': movieId,
  'source_id': sourceId,
  'status': status,
  'remote_percent': 0,
  'error_code': null,
  'media_candidates': <Object?>[],
  'selected_media_ids': <Object?>[],
  'subtitles': <Object?>[],
  'ready_at': status == 'ready' ? '2026-07-31T12:00:59Z' : null,
  'expires_at': null,
  'created_at': '2026-07-31T12:00:00Z',
  'updated_at': '2026-07-31T12:00:00Z',
};

CacheJobDto _job(String status) => CacheJobDto.fromJson(_jobJson(status));

SnapshotState _snapshot(CacheJobDto job, {int version = 1}) =>
    SnapshotState.empty().copyWith(
      snapshotVersion: version,
      cacheJobs: <String, CacheJobDto>{job.id: job},
    );

NotificationDto _notification(String type, {String? errorCode}) =>
    NotificationDto(
      id: notificationId,
      type: type,
      resourceId: jobId,
      errorCode: errorCode,
      createdAt: DateTime.utc(2026, 7, 31),
      readAt: null,
    );

class _PlayGateway implements PlayRequestGateway {
  _PlayGateway({this.next, this.pending});

  PlayRequestResultDto? next;
  final Completer<PlayRequestResultDto>? pending;
  ApiException? cancelError;
  int calls = 0;
  final List<String> keys = <String>[];
  final List<bool> cancelConfirmed = <bool>[];

  @override
  Future<PlayRequestResultDto> request({
    required String movieId,
    required String sourceId,
    required String idempotencyKey,
  }) {
    calls++;
    keys.add(idempotencyKey);
    return pending?.future ?? Future<PlayRequestResultDto>.value(next);
  }

  @override
  Future<CacheJobDto> cancel(String jobId, {required bool confirmed}) async {
    cancelConfirmed.add(confirmed);
    final error = cancelError;
    if (error != null) throw error;
    return _job('cleaned');
  }
}

class _TestClock implements PlayRequestClock {
  DateTime wall = DateTime.utc(2026, 7, 31, 12);
  Duration elapsed = Duration.zero;

  void advance(Duration duration) {
    wall = wall.add(duration);
    elapsed += duration;
  }

  @override
  DateTime wallNow() => wall;

  @override
  Duration monotonicNow() => elapsed;
}

class _ToastPort implements CacheToastPort {
  Object? failure;
  void Function(String? payload)? activate;
  String? title;
  String? body;
  String? payload;

  @override
  Future<void> initialize(void Function(String? payload) onActivated) async {
    if (failure != null) throw failure!;
    activate = onActivated;
  }

  @override
  Future<void> show({
    required int id,
    required String title,
    required String body,
    required String payload,
  }) async {
    if (failure != null) throw failure!;
    this.title = title;
    this.body = body;
    this.payload = payload;
  }
}

class _RecordingApiClient implements ApiClient {
  String? path;
  Map<String, Object?>? data;
  Map<String, Object?>? headers;

  @override
  Future<T> post<T>(
    String path, {
    Map<String, Object?>? data,
    Map<String, Object?>? query,
    Map<String, Object?>? headers,
    required T Function(Map<String, Object?> json) decode,
  }) async {
    this.path = path;
    this.data = data;
    this.headers = headers;
    return decode(_resultJson(PlayDisposition.started));
  }

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError(invocation.memberName.toString());
}

const movieId = '00000000-0000-4000-8000-000000000101';
const sourceId = '00000000-0000-4000-8000-000000000102';
const jobId = '00000000-0000-4000-8000-000000000103';
const notificationId = '00000000-0000-4000-8000-000000000104';

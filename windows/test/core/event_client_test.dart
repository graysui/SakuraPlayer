import 'dart:async';
import 'dart:convert';

import 'package:flutter/widgets.dart' show AppLifecycleState;
import 'package:flutter_test/flutter_test.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/core/events/app_lifecycle.dart';
import 'package:sakuraplayer_windows/core/events/event_client.dart';
import 'package:sakuraplayer_windows/core/events/snapshot_controller.dart';

void main() {
  group('snapshot merge', () {
    test('cache events refresh authoritative capacity counters', () async {
      var loads = 0;
      final controller = SnapshotController(
        loadSnapshot: () async {
          loads++;
          return _snapshot(
            version: loads == 1 ? 100 : 101,
            queues:
                loads == 1
                    ? const QueueSnapshot(
                      metadataQueued: 0,
                      metadataRunning: 0,
                      cacheQueued: 0,
                      cacheRunning: 1,
                      cacheReady: 0,
                    )
                    : const QueueSnapshot(
                      metadataQueued: 0,
                      metadataRunning: 0,
                      cacheQueued: 0,
                      cacheRunning: 0,
                      cacheReady: 1,
                    ),
          );
        },
      );
      await controller.recover();

      expect(
        await controller.apply(
          EventEnvelope.fromJson(
            _cacheEvent(
              eventId: _uuid(10),
              sequence: 101,
              streamVersion: 8,
              percent: 100,
              status: 'ready',
            ),
          ),
        ),
        EventApplyResult.recovered,
      );
      expect(loads, 2);
      expect(controller.state.queues.cacheRunning, 0);
      expect(controller.state.queues.cacheReady, 1);
    });

    test(
      'catalog core-ready is observable without a redundant snapshot',
      () async {
        var loads = 0;
        final controller = SnapshotController(
          loadSnapshot: () async {
            loads++;
            return _snapshot(version: 100);
          },
        );
        await controller.recover();

        expect(
          await controller.apply(
            EventEnvelope.fromJson(<String, Object?>{
              'version': 1,
              'event_id': _uuid(9),
              'sequence': 101,
              'stream': 'catalog',
              'stream_version': 1,
              'type': 'catalog.movie.core_ready.v1',
              'occurred_at': '2026-07-29T12:00:00Z',
              'resource': <String, Object?>{
                'movie_id': _movieId,
                'number': 'ABC-123',
              },
            }),
          ),
          EventApplyResult.applied,
        );
        expect(loads, 1);
        expect(controller.state.catalogReadyRevision, 1);
        expect(controller.state.lastCatalogMovieReady?.number, 'ABC-123');
      },
    );

    test(
      'first event after snapshot establishes unknown aggregate version',
      () async {
        var loads = 0;
        final controller = SnapshotController(
          loadSnapshot: () async {
            loads++;
            return _snapshot(version: 100);
          },
        );
        await controller.recover();

        final first = EventEnvelope.fromJson(
          _cacheEvent(
            eventId: _uuid(11),
            sequence: 101,
            streamVersion: 8,
            percent: 25,
          ),
        );
        expect(await controller.apply(first), EventApplyResult.applied);
        expect(controller.state.cacheJobs[_cacheId]!.remotePercent, 25);
        expect(loads, 1);

        expect(await controller.apply(first), EventApplyResult.ignored);
        expect(loads, 1);

        final next = EventEnvelope.fromJson(
          _cacheEvent(
            eventId: _uuid(12),
            sequence: 102,
            streamVersion: 9,
            percent: 40,
          ),
        );
        expect(await controller.apply(next), EventApplyResult.applied);
        expect(controller.state.cacheJobs[_cacheId]!.remotePercent, 40);
      },
    );

    test(
      'sequence or established aggregate gap triggers one snapshot',
      () async {
        var loads = 0;
        final controller = SnapshotController(
          loadSnapshot: () async {
            loads++;
            return _snapshot(version: loads == 1 ? 100 : 110);
          },
        );
        await controller.recover();
        await controller.apply(
          EventEnvelope.fromJson(
            _cacheEvent(
              eventId: _uuid(21),
              sequence: 101,
              streamVersion: 3,
              percent: 10,
            ),
          ),
        );

        final result = await Future.wait(<Future<EventApplyResult>>[
          controller.apply(
            EventEnvelope.fromJson(
              _cacheEvent(
                eventId: _uuid(22),
                sequence: 102,
                streamVersion: 5,
                percent: 20,
              ),
            ),
          ),
          controller.apply(
            EventEnvelope.fromJson(
              _cacheEvent(
                eventId: _uuid(23),
                sequence: 104,
                streamVersion: 6,
                percent: 30,
              ),
            ),
          ),
        ]);

        expect(result, everyElement(EventApplyResult.recovered));
        expect(loads, 2);
        expect(controller.state.snapshotVersion, 110);
      },
    );

    test(
      'missing local resource and unknown event version require recovery',
      () async {
        var loads = 0;
        final controller = SnapshotController(
          loadSnapshot: () async {
            loads++;
            return _snapshot(version: loads == 1 ? 100 : 101);
          },
        );
        await controller.recover();
        final missing = _cacheEvent(
          eventId: _uuid(31),
          sequence: 101,
          streamVersion: 1,
          percent: 1,
        );
        (missing['resource']! as Map<String, Object?>)['id'] = _uuid(999);

        expect(
          await controller.apply(EventEnvelope.fromJson(missing)),
          EventApplyResult.recovered,
        );
        expect(loads, 2);

        final unknown = _cacheEvent(
          eventId: _uuid(32),
          sequence: 102,
          streamVersion: 2,
          percent: 2,
        )..['type'] = 'cache.job.updated.v2';
        expect(
          () => EventEnvelope.fromJson(unknown),
          throwsA(isA<ProtocolException>()),
        );
      },
    );
  });

  group('notifications', () {
    test('marks unread only after sink confirms display', () async {
      final sink = _NotificationSink(result: true);
      var marks = 0;
      final coordinator = NotificationCoordinator(
        sink: sink,
        markRead: (id) async {
          marks++;
          return _notification(readAt: DateTime.utc(2026, 7, 29, 12, 1));
        },
      );
      final controller = SnapshotController(
        loadSnapshot:
            () async => _snapshot(
              version: 100,
              notifications: <NotificationDto>[_notification()],
            ),
        notifications: coordinator,
      );

      await controller.recover();

      expect(sink.shown, 1);
      expect(marks, 1);
      expect(
        controller.state.notifications[_notificationId]!.readAt,
        isNotNull,
      );
    });

    test('does not mark read when platform sink did not display', () async {
      final sink = _NotificationSink(result: false);
      var marks = 0;
      final controller = SnapshotController(
        loadSnapshot:
            () async => _snapshot(
              version: 100,
              notifications: <NotificationDto>[_notification()],
            ),
        notifications: NotificationCoordinator(
          sink: sink,
          markRead: (id) async {
            marks++;
            return _notification(readAt: DateTime.now().toUtc());
          },
        ),
      );

      await controller.recover();

      expect(sink.shown, 1);
      expect(marks, 0);
      expect(controller.state.notifications[_notificationId]!.readAt, isNull);
    });
  });

  testWidgets('lifecycle listener registers and unregisters', (tester) async {
    final seen = <AppVisibility>[];
    final lifecycle = AppLifecycleCoordinator(
      onVisibilityChanged: (value) async => seen.add(value),
    );

    lifecycle.register();
    expect(lifecycle.isRegistered, isTrue);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    await tester.pump();
    expect(seen, <AppVisibility>[AppVisibility.background]);

    lifecycle.unregister();
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump();
    expect(seen, hasLength(1));
    expect(lifecycle.isRegistered, isFalse);
  });

  test(
    'event client authenticates, recovers unknown messages and closes',
    () async {
      var loads = 0;
      final snapshots = SnapshotController(
        loadSnapshot: () async => _snapshot(version: 100 + loads++),
      );
      final connector = _EventConnector();
      final client = EventClient(
        serverBaseUri: Uri.parse('https://server.test'),
        accessToken: () => 'access-token',
        reauthenticate: () async {},
        snapshots: snapshots,
        connector: connector,
        reconnectDelay: const Duration(milliseconds: 1),
        pingInterval: const Duration(hours: 1),
      );

      await client.start();
      expect(connector.uri.toString(), 'wss://server.test/api/v1/events/ws');
      expect(connector.token, 'access-token');
      expect(loads, 1);

      connector.connection.controller.add(
        jsonEncode(<String, Object?>{'version': 2, 'type': 'future.event.v2'}),
      );
      await Future<void>.delayed(const Duration(milliseconds: 10));
      expect(loads, 2);

      await client.handleVisibility(AppVisibility.background);
      expect(connector.connection.closed, isFalse);
      await client.handleVisibility(AppVisibility.detached);
      expect(connector.connection.closed, isTrue);
    },
  );

  test(
    'close code 4409 snapshots and reconnects without auth refresh',
    () async {
      var loads = 0;
      var refreshes = 0;
      final snapshots = SnapshotController(
        loadSnapshot: () async => _snapshot(version: 100 + loads++),
      );
      final connector = _EventConnector();
      final client = EventClient(
        serverBaseUri: Uri.parse('https://server.test'),
        accessToken: () => 'access-token',
        reauthenticate: () async {
          refreshes++;
        },
        snapshots: snapshots,
        connector: connector,
        reconnectDelay: const Duration(milliseconds: 1),
        pingInterval: const Duration(hours: 1),
      );
      await client.start();
      connector.connection.code = 4409;
      await connector.connection.close();
      await Future<void>.delayed(const Duration(milliseconds: 20));

      expect(connector.connections, hasLength(2));
      expect(loads, 2);
      expect(refreshes, 0);
      await client.dispose();
    },
  );

  test('initial connection failure schedules an automatic retry', () async {
    var loads = 0;
    final snapshots = SnapshotController(
      loadSnapshot: () async => _snapshot(version: 100 + loads++),
    );
    final connector = _EventConnector(failuresRemaining: 1);
    final client = EventClient(
      serverBaseUri: Uri.parse('https://server.test'),
      accessToken: () => 'access-token',
      reauthenticate: () async {},
      snapshots: snapshots,
      connector: connector,
      reconnectDelay: const Duration(milliseconds: 1),
      pingInterval: const Duration(hours: 1),
    );

    await client.start();
    await Future<void>.delayed(const Duration(milliseconds: 20));

    expect(connector.attempts, 2);
    expect(connector.connections, hasLength(1));
    expect(client.isConnected, isTrue);
    expect(loads, 2);
    await client.dispose();
  });
}

const _cacheId = '00000000-0000-4000-8000-000000000001';
const _movieId = '00000000-0000-4000-8000-000000000002';
const _sourceId = '00000000-0000-4000-8000-000000000003';
const _notificationId = '00000000-0000-4000-8000-000000000004';

String _uuid(int value) =>
    '00000000-0000-4000-8000-${value.toString().padLeft(12, '0')}';

EventSnapshotDto _snapshot({
  required int version,
  QueueSnapshot queues = const QueueSnapshot(
    metadataQueued: 0,
    metadataRunning: 0,
    cacheQueued: 0,
    cacheRunning: 1,
    cacheReady: 0,
  ),
  List<NotificationDto> notifications = const <NotificationDto>[],
}) => EventSnapshotDto(
  snapshotVersion: version,
  lastEventId: _uuid(version),
  queues: queues,
  cacheJobs: <CacheJobDto>[_cacheJob()],
  metadataJobs: const <MetadataJobDto>[],
  cloud115Binding: const Cloud115BindingDto(
    bound: false,
    status: 'unbound',
    displayName: null,
    cacheRootReady: false,
    lastVerifiedAt: null,
  ),
  notifications: notifications,
);

CacheJobDto _cacheJob() => CacheJobDto(
  id: _cacheId,
  movieId: _movieId,
  sourceId: _sourceId,
  status: 'offlining',
  remotePercent: 0,
  errorCode: null,
  mediaCandidates: const <RemoteMediaDto>[],
  selectedMediaIds: const <String>[],
  subtitles: const <SubtitleOptionDto>[],
  readyAt: null,
  expiresAt: null,
  createdAt: DateTime.utc(2026, 7, 29, 12),
  updatedAt: DateTime.utc(2026, 7, 29, 12),
);

NotificationDto _notification({DateTime? readAt}) => NotificationDto(
  id: _notificationId,
  type: 'cache_ready',
  resourceId: _cacheId,
  errorCode: null,
  createdAt: DateTime.utc(2026, 7, 29, 12),
  readAt: readAt,
);

Map<String, Object?> _cacheEvent({
  required String eventId,
  required int sequence,
  required int streamVersion,
  required num percent,
  String status = 'offlining',
}) => <String, Object?>{
  'version': 1,
  'event_id': eventId,
  'sequence': sequence,
  'stream': 'cache',
  'stream_version': streamVersion,
  'type': 'cache.job.updated.v1',
  'occurred_at': '2026-07-29T12:00:00Z',
  'resource': <String, Object?>{
    'id': _cacheId,
    'status': status,
    'remote_percent': percent,
    'error_code': null,
    'updated_at': '2026-07-29T12:00:01Z',
  },
};

class _NotificationSink implements AppNotificationSink {
  _NotificationSink({required this.result});

  final bool result;
  int shown = 0;

  @override
  Future<bool> show(NotificationDto notification) async {
    shown++;
    return result;
  }
}

class _EventConnector implements EventConnector {
  _EventConnector({this.failuresRemaining = 0});

  final List<_EventConnection> connections = <_EventConnection>[];
  int failuresRemaining;
  int attempts = 0;
  late Uri uri;
  late String token;

  _EventConnection get connection => connections.last;

  @override
  Future<EventConnection> connect(
    Uri uri, {
    required String accessToken,
  }) async {
    attempts++;
    if (failuresRemaining > 0) {
      failuresRemaining--;
      throw Exception('fixture connection failure');
    }
    this.uri = uri;
    token = accessToken;
    final connection = _EventConnection();
    connections.add(connection);
    return connection;
  }
}

class _EventConnection implements EventConnection {
  final StreamController<Object?> controller = StreamController<Object?>();
  bool closed = false;
  int? code;

  @override
  int? get closeCode => code;

  @override
  Stream<Object?> get messages => controller.stream;

  @override
  Future<void> close() async {
    closed = true;
    await controller.close();
  }

  @override
  void send(Object message) {}
}

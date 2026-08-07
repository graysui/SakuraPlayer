import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/core/auth/session_store.dart';
import 'package:sakuraplayer_windows/core/storage/secure_store.dart';
import 'package:sakuraplayer_windows/features/cache/data/cache_api.dart';
import 'package:sakuraplayer_windows/features/cache/presentation/cache_controller.dart';
import 'package:sakuraplayer_windows/features/cache/presentation/cache_page.dart';

void main() {
  group('cache contract', () {
    test('maps all 13 states and exposes only authoritative actions', () {
      expect(cacheStatusLabels.keys, cacheJobStatuses);
      for (final status in cacheJobStatuses) {
        expect(cacheStatusLabels[status], isNotEmpty);
      }

      expect(canCancelCacheStatus('queued'), isTrue);
      expect(canCancelCacheStatus('resolving'), isTrue);
      expect(canCancelCacheStatus('ready'), isFalse);
      expect(canCleanupCacheStatus('awaiting_selection'), isTrue);
      expect(canCleanupCacheStatus('cleanup_failed'), isTrue);
      expect(canCleanupCacheStatus('failed'), isFalse);
    });

    test('parses fixed capacity and rejects duplicate jobs', () {
      final page = CacheJobPageDto.fromJson(<String, Object?>{
        'items': <Object?>[_jobJson()],
        'capacity': <String, Object?>{
          'running': 1,
          'running_limit': 2,
          'queued': 2,
          'queued_limit': 10,
          'ready': 3,
          'ready_limit': 20,
        },
        'next_cursor': null,
      });

      expect(page.capacity.runningLimit, 2);
      expect(page.capacity.queuedLimit, 10);
      expect(page.capacity.readyLimit, 20);
      expect(
        () => CacheJobPageDto.fromJson(<String, Object?>{
          'items': <Object?>[_jobJson(), _jobJson()],
          'capacity': <String, Object?>{
            'running': 1,
            'running_limit': 2,
            'queued': 2,
            'queued_limit': 10,
            'ready': 3,
            'ready_limit': 20,
          },
          'next_cursor': null,
        }),
        throwsA(isA<ProtocolException>()),
      );
    });

    test(
      'gateway uses comma status query and confirmed cancellation',
      () async {
        final session = SessionStore(SecureStore(MemorySecureKeyValueStore()));
        await session.setTokens(
          TokenPair(
            accessToken: 'access-token',
            refreshToken: 'refresh-token',
            accessExpiresAt: DateTime.utc(2026, 7, 30, 13),
            refreshExpiresAt: DateTime.utc(2026, 8, 30),
          ),
        );
        final adapter = _CacheAdapter();
        final dio = Dio(BaseOptions(baseUrl: 'https://server.test/api/v1/'))
          ..httpClientAdapter = adapter;
        final api = CacheApi(ApiClient(dio: dio, sessionStore: session));

        await api.listJobs(statuses: const <String>{'ready', 'queued'});
        await api.cancel(_jobId);
        await api.selectMedia(_jobId, const [_mediaId1, _mediaId2]);

        expect(
          adapter.requests.first.queryParameters['status'],
          'queued,ready',
        );
        expect(adapter.requests.first.queryParameters['limit'], 24);
        expect(adapter.requests[1].data, <String, Object?>{'confirmed': true});
        expect(adapter.requests[1].path, 'cache-jobs/$_jobId/cancel');
        expect(
          adapter.requests.last.path,
          'cache-jobs/$_jobId/media-selection',
        );
        expect(adapter.requests.last.data, <String, Object?>{
          'media_ids': <String>[_mediaId1, _mediaId2],
        });
      },
    );

    test('groups valid candidate segments in sequence order', () {
      final job = CacheJobDto.fromJson(
        _jobJson()
          ..['status'] = 'awaiting_selection'
          ..['media_candidates'] = <Object?>[
            _mediaJson(_mediaId2, _candidateId, 2, 'part-2.mp4'),
            _mediaJson(_invalidMediaId, _candidateId, 3, 'invalid.mp4', false),
            _mediaJson(_mediaId1, _candidateId, 1, 'part-1.mp4'),
          ],
      );

      final groups = validMediaCandidateGroups(job);

      expect(groups, hasLength(1));
      expect(groups.single.media.map((item) => item.id), [
        _mediaId1,
        _mediaId2,
      ]);
    });
  });

  test(
    'controller requires confirmation and blocks duplicate cancellation',
    () async {
      final gateway = _CacheGateway();
      final container = ProviderContainer(
        overrides: [cacheGatewayProvider.overrideWithValue(gateway)],
      );
      addTearDown(container.dispose);
      final controller = container.read(cacheControllerProvider.notifier);
      await controller.loadInitial();

      await controller.cancel(_jobId, confirmed: false);
      expect(gateway.cancelCalls, 0);

      final first = controller.cancel(_jobId, confirmed: true);
      final duplicate = controller.cancel(_jobId, confirmed: true);
      expect(gateway.cancelCalls, 1);
      gateway.completeCancel(_job('cancelling'));
      await Future.wait(<Future<void>>[first, duplicate]);

      expect(
        container.read(cacheControllerProvider).items.single.status,
        'cancelling',
      );
      expect(container.read(cacheControllerProvider).inFlightIds, isEmpty);
    },
  );

  test(
    'refresh during in-flight action clears spinner state',
    () async {
      final gateway = _CacheGateway();
      final container = ProviderContainer(
        overrides: [cacheGatewayProvider.overrideWithValue(gateway)],
      );
      addTearDown(container.dispose);
      final controller = container.read(cacheControllerProvider.notifier);
      await controller.loadInitial();

      // 发起取消并保持请求在途。
      final pending = controller.cancel(_jobId, confirmed: true);
      expect(
        container.read(cacheControllerProvider).inFlightIds,
        contains(_jobId),
      );

      // 列表刷新（generation 变化）后按钮不得残留转圈状态。
      await controller.refresh();
      expect(container.read(cacheControllerProvider).inFlightIds, isEmpty);

      // 迟到的在途响应被丢弃且不复活转圈状态。
      gateway.completeCancel(_job('cancelling'));
      await pending;
      expect(container.read(cacheControllerProvider).inFlightIds, isEmpty);
    },
  );

  test(
    'cleanupAll serially cleans only cleanable jobs',
    () async {
      final gateway = _CleanupAllGateway();
      final container = ProviderContainer(
        overrides: [cacheGatewayProvider.overrideWithValue(gateway)],
      );
      addTearDown(container.dispose);
      final controller = container.read(cacheControllerProvider.notifier);
      await controller.loadInitial();

      await controller.cleanupAll();

      expect(gateway.cleanupCalls, 2);
      expect(container.read(cacheControllerProvider).inFlightIds, isEmpty);
      final byId = <String, String>{
        for (final item in container.read(cacheControllerProvider).items)
          item.id: item.status,
      };
      expect(byId[_jobId], 'queued');
      expect(byId[_CleanupAllGateway.readyJobId], 'cleaning');
      expect(byId[_CleanupAllGateway.failedJobId], 'cleaning');
    },
  );

  testWidgets('page shows fixed capacity and confirms cancellation', (
    tester,
  ) async {
    final gateway = _WidgetCacheGateway();
    tester.view.physicalSize = const Size(1200, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [cacheGatewayProvider.overrideWithValue(gateway)],
        child: const MaterialApp(home: Scaffold(body: CachePage())),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('1 / 2'), findsOneWidget);
    expect(find.text('2 / 10'), findsOneWidget);
    expect(find.text('3 / 20'), findsOneWidget);
    expect(
      tester.getSize(find.byKey(const ValueKey('capacity-运行'))).height,
      82,
    );
    expect(
      tester.getSize(find.byKey(const ValueKey('cache-job-$_jobId'))).height,
      greaterThanOrEqualTo(96),
    );
    // 没有可清理任务时不显示一键清理按钮。
    expect(find.text('一键清理'), findsNothing);
    await tester.tap(find.byTooltip('取消任务'));
    await tester.pumpAndSettle();
    expect(find.text('取消缓存任务？'), findsOneWidget);
    expect(gateway.cancelCalls, 0);
    await tester.tap(find.text('确认'));
    await tester.pumpAndSettle();
    expect(gateway.cancelCalls, 1);
    expect(find.text('正在取消'), findsOneWidget);
  });

  testWidgets('one-click cleanup confirms and cleans all cleanable jobs', (
    tester,
  ) async {
    final gateway = _CleanupAllGateway();
    tester.view.physicalSize = const Size(1200, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [cacheGatewayProvider.overrideWithValue(gateway)],
        child: const MaterialApp(home: Scaffold(body: CachePage())),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('一键清理'), findsOneWidget);
    await tester.tap(find.text('一键清理'));
    await tester.pumpAndSettle();
    expect(find.text('清理所有缓存？'), findsOneWidget);
    await tester.tap(find.text('确认'));
    await tester.pumpAndSettle();
    expect(gateway.cleanupCalls, 2);
  });

  testWidgets('candidate selection submits full group before explicit play', (
    tester,
  ) async {
    final gateway = _SelectionCacheGateway();
    final launches = <(String, String)>[];
    await tester.pumpWidget(
      ProviderScope(
        overrides: [cacheGatewayProvider.overrideWithValue(gateway)],
        child: MaterialApp(
          home: Scaffold(
            body: CachePage(
              onPlay: (jobId, mediaId) => launches.add((jobId, mediaId)),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(
      find.byKey(const ValueKey('select-candidate-$_candidateId')),
    );
    await tester.pumpAndSettle();

    expect(gateway.selectedIds, [_mediaId1, _mediaId2]);
    expect(launches, [(_jobId, _mediaId1)]);
  });
}

const _jobId = '00000000-0000-4000-8000-000000000208';
const _candidateId = '00000000-0000-4000-8000-000000000301';
const _mediaId1 = '00000000-0000-4000-8000-000000000302';
const _mediaId2 = '00000000-0000-4000-8000-000000000303';
const _invalidMediaId = '00000000-0000-4000-8000-000000000304';

Map<String, Object?> _jobJson() => <String, Object?>{
  'id': _jobId,
  'movie_id': '00000000-0000-4000-8000-000000000101',
  'source_id': '00000000-0000-4000-8000-000000000201',
  'status': 'queued',
  'remote_percent': 0,
  'error_code': null,
  'media_candidates': <Object?>[],
  'selected_media_ids': <Object?>[],
  'subtitles': <Object?>[],
  'ready_at': null,
  'expires_at': null,
  'created_at': '2026-07-30T12:00:00Z',
  'updated_at': '2026-07-30T12:00:00Z',
};

CacheJobDto _job(String status) =>
    CacheJobDto.fromJson(_jobJson()..['status'] = status);

Map<String, Object?> _mediaJson(
  String id,
  String candidateId,
  int sequence,
  String name, [
  bool valid = true,
]) => <String, Object?>{
  'id': id,
  'candidate_id': candidateId,
  'name': name,
  'size_bytes': 1024,
  'duration_seconds': 60,
  'sequence_no': sequence,
  'is_valid': valid,
};

class _CacheGateway implements CacheGateway {
  final _cancelCompleter = Completer<CacheJobDto>();
  int cancelCalls = 0;

  @override
  Future<CacheJobPageDto> listJobs({
    Set<String> statuses = const <String>{},
    String? cursor,
  }) async => CacheJobPageDto.fromJson(<String, Object?>{
    'items': <Object?>[_jobJson()],
    'capacity': <String, Object?>{
      'running': 0,
      'running_limit': 2,
      'queued': 1,
      'queued_limit': 10,
      'ready': 0,
      'ready_limit': 20,
    },
    'next_cursor': null,
  });

  @override
  Future<CacheJobDto> cancel(String jobId) {
    cancelCalls++;
    return _cancelCompleter.future;
  }

  void completeCancel(CacheJobDto job) => _cancelCompleter.complete(job);

  @override
  Future<CacheJobDto> cleanup(String jobId) => throw UnimplementedError();

  @override
  Future<CacheJobDto> selectMedia(String jobId, List<String> mediaIds) =>
      throw UnimplementedError();
}

class _WidgetCacheGateway implements CacheGateway {
  int cancelCalls = 0;
  @override
  Future<CacheJobPageDto> listJobs({
    Set<String> statuses = const <String>{},
    String? cursor,
  }) async => CacheJobPageDto.fromJson(<String, Object?>{
    'items': <Object?>[_jobJson()],
    'capacity': <String, Object?>{
      'running': 1,
      'running_limit': 2,
      'queued': 2,
      'queued_limit': 10,
      'ready': 3,
      'ready_limit': 20,
    },
    'next_cursor': null,
  });
  @override
  Future<CacheJobDto> cancel(String jobId) async {
    cancelCalls++;
    return _job('cancelling');
  }

  @override
  Future<CacheJobDto> cleanup(String jobId) async => _job('cleaning');

  @override
  Future<CacheJobDto> selectMedia(String jobId, List<String> mediaIds) =>
      throw UnimplementedError();
}

class _CleanupAllGateway implements CacheGateway {
  int cleanupCalls = 0;
  static const readyJobId = '00000000-0000-4000-8000-000000000209';
  static const failedJobId = '00000000-0000-4000-8000-000000000210';

  @override
  Future<CacheJobPageDto> listJobs({
    Set<String> statuses = const <String>{},
    String? cursor,
  }) async => CacheJobPageDto.fromJson(<String, Object?>{
    'items': <Object?>[
      _jobJson(), // queued，不可清理
      _jobJson()
        ..['id'] = readyJobId
        ..['status'] = 'ready',
      _jobJson()
        ..['id'] = failedJobId
        ..['status'] = 'cleanup_failed',
    ],
    'capacity': <String, Object?>{
      'running': 0,
      'running_limit': 2,
      'queued': 1,
      'queued_limit': 10,
      'ready': 2,
      'ready_limit': 20,
    },
    'next_cursor': null,
  });

  @override
  Future<CacheJobDto> cleanup(String jobId) async {
    cleanupCalls++;
    return CacheJobDto.fromJson(
      _jobJson()
        ..['id'] = jobId
        ..['status'] = 'cleaning',
    );
  }

  @override
  Future<CacheJobDto> cancel(String jobId) => throw UnimplementedError();
  @override
  Future<CacheJobDto> selectMedia(String jobId, List<String> mediaIds) =>
      throw UnimplementedError();
}

class _SelectionCacheGateway implements CacheGateway {  List<String> selectedIds = const [];

  Map<String, Object?> get _selectionJob =>
      _jobJson()
        ..['status'] = 'awaiting_selection'
        ..['media_candidates'] = <Object?>[
          _mediaJson(_mediaId2, _candidateId, 2, 'part-2.mp4'),
          _mediaJson(_mediaId1, _candidateId, 1, 'part-1.mp4'),
        ];

  @override
  Future<CacheJobPageDto> listJobs({
    Set<String> statuses = const <String>{},
    String? cursor,
  }) async => CacheJobPageDto.fromJson(<String, Object?>{
    'items': <Object?>[_selectionJob],
    'capacity': <String, Object?>{
      'running': 0,
      'running_limit': 2,
      'queued': 0,
      'queued_limit': 10,
      'ready': 0,
      'ready_limit': 20,
    },
    'next_cursor': null,
  });

  @override
  Future<CacheJobDto> selectMedia(String jobId, List<String> mediaIds) async {
    selectedIds = List.unmodifiable(mediaIds);
    return CacheJobDto.fromJson(
      _selectionJob
        ..['status'] = 'ready'
        ..['selected_media_ids'] = mediaIds,
    );
  }

  @override
  Future<CacheJobDto> cancel(String jobId) => throw UnimplementedError();
  @override
  Future<CacheJobDto> cleanup(String jobId) => throw UnimplementedError();
}

class _CacheAdapter implements HttpClientAdapter {
  final requests = <RequestOptions>[];
  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options);
    if (options.method == 'GET') {
      return _cacheJsonResponse(200, <String, Object?>{
        'items': <Object?>[_jobJson()],
        'capacity': <String, Object?>{
          'running': 0,
          'running_limit': 2,
          'queued': 1,
          'queued_limit': 10,
          'ready': 0,
          'ready_limit': 20,
        },
        'next_cursor': null,
      });
    }
    if (options.method == 'POST') {
      return _cacheJsonResponse(202, _jobJson()..['status'] = 'cancelling');
    }
    if (options.method == 'PUT') {
      return _cacheJsonResponse(
        200,
        _jobJson()
          ..['status'] = 'ready'
          ..['selected_media_ids'] = <String>[_mediaId1, _mediaId2],
      );
    }
    throw StateError('unexpected ${options.method} ${options.path}');
  }

  @override
  void close({bool force = false}) {}
}

ResponseBody _cacheJsonResponse(int status, Map<String, Object?> body) =>
    ResponseBody.fromString(
      jsonEncode(body),
      status,
      headers: <String, List<String>>{
        Headers.contentTypeHeader: <String>['application/json'],
      },
    );

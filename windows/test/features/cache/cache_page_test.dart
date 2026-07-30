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

        expect(
          adapter.requests.first.queryParameters['status'],
          'queued,ready',
        );
        expect(adapter.requests.first.queryParameters['limit'], 24);
        expect(adapter.requests.last.data, <String, Object?>{
          'confirmed': true,
        });
        expect(adapter.requests.last.path, 'cache-jobs/$_jobId/cancel');
      },
    );
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
    await tester.tap(find.byTooltip('取消任务'));
    await tester.pumpAndSettle();
    expect(find.text('取消缓存任务？'), findsOneWidget);
    expect(gateway.cancelCalls, 0);
    await tester.tap(find.text('确认'));
    await tester.pumpAndSettle();
    expect(gateway.cancelCalls, 1);
    expect(find.text('正在取消'), findsOneWidget);
  });
}

const _jobId = '00000000-0000-4000-8000-000000000208';

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

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/core/events/snapshot_controller.dart';
import 'package:sakuraplayer_windows/features/cache/data/play_request_api.dart';
import 'package:sakuraplayer_windows/features/cache/presentation/blocking_wait_page.dart';
import 'package:sakuraplayer_windows/features/cache/presentation/play_request_controller.dart';

void main() {
  testWidgets('blocks back and exposes only confirmed cancellation', (
    tester,
  ) async {
    final gateway = _Gateway();
    final container = ProviderContainer(
      overrides: [
        playRequestGatewayProvider.overrideWithValue(gateway),
        playRequestClockProvider.overrideWithValue(_Clock()),
      ],
    );
    addTearDown(container.dispose);
    await container
        .read(playRequestControllerProvider.notifier)
        .submit(movieId: movieId, sourceId: sourceId);
    var cancelled = 0;

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp(
          home: BlockingWaitPage(
            onReady: () {},
            onTimedOut: () {},
            onCancelled: () => cancelled++,
            onStopped: () {},
          ),
        ),
      ),
    );
    await tester.pump();

    expect(find.text('正在准备播放'), findsOneWidget);
    expect(find.textContaining('2 个运行'), findsOneWidget);
    expect(find.textContaining('10 个排队'), findsOneWidget);
    expect(find.byType(TextField), findsNothing);
    expect(find.byType(Slider), findsNothing);

    await tester.binding.handlePopRoute();
    await tester.pump();
    expect(find.byType(BlockingWaitPage), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('wait-cancel')));
    await tester.pumpAndSettle();
    expect(find.text('取消缓存任务？'), findsOneWidget);
    await tester.tap(find.text('返回等待'));
    await tester.pumpAndSettle();
    expect(gateway.cancelCalls, 0);

    await tester.tap(find.byKey(const ValueKey('wait-cancel')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('确认取消'));
    await tester.pumpAndSettle();
    expect(gateway.cancelCalls, 1);
    expect(cancelled, 1);
  });

  testWidgets('ready snapshot opens player once', (tester) async {
    final gateway = _Gateway();
    final container = ProviderContainer(
      overrides: [
        playRequestGatewayProvider.overrideWithValue(gateway),
        playRequestClockProvider.overrideWithValue(_Clock()),
      ],
    );
    addTearDown(container.dispose);
    await container
        .read(playRequestControllerProvider.notifier)
        .submit(movieId: movieId, sourceId: sourceId);
    var ready = 0;

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp(
          home: BlockingWaitPage(
            onReady: () => ready++,
            onTimedOut: () {},
            onCancelled: () {},
            onStopped: () {},
          ),
        ),
      ),
    );
    await tester.pump();
    container
        .read(snapshotStateProvider.notifier)
        .replace(
          SnapshotState.empty().copyWith(
            snapshotVersion: 1,
            cacheJobs: <String, CacheJobDto>{jobId: _job('ready')},
          ),
        );
    await tester.pump();
    expect(ready, 1);

    container
        .read(snapshotStateProvider.notifier)
        .replace(
          SnapshotState.empty().copyWith(
            snapshotVersion: 2,
            cacheJobs: <String, CacheJobDto>{jobId: _job('ready')},
          ),
        );
    await tester.pump();
    expect(ready, 1);
  });

  testWidgets('cancel failure keeps the blocking page and shows stable code', (
    tester,
  ) async {
    final gateway = _Gateway(cancelError: true);
    final container = ProviderContainer(
      overrides: [
        playRequestGatewayProvider.overrideWithValue(gateway),
        playRequestClockProvider.overrideWithValue(_Clock()),
      ],
    );
    addTearDown(container.dispose);
    await container
        .read(playRequestControllerProvider.notifier)
        .submit(movieId: movieId, sourceId: sourceId);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp(
          home: BlockingWaitPage(
            onReady: () {},
            onTimedOut: () {},
            onCancelled: () {},
            onStopped: () {},
          ),
        ),
      ),
    );
    await tester.tap(find.byKey(const ValueKey('wait-cancel')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('确认取消'));
    await tester.pumpAndSettle();

    expect(find.byType(BlockingWaitPage), findsOneWidget);
    expect(find.textContaining('cache_active_lease'), findsOneWidget);
    container.read(playRequestControllerProvider.notifier).reset();
    await tester.pump();
  });
}

class _Gateway implements PlayRequestGateway {
  _Gateway({this.cancelError = false});

  final bool cancelError;
  int cancelCalls = 0;

  @override
  Future<PlayRequestResultDto> request({
    required String movieId,
    required String sourceId,
    required String idempotencyKey,
  }) async => PlayRequestResultDto(
    disposition: PlayDisposition.started,
    waitDeadline: DateTime.utc(2026, 7, 31, 12, 1),
    cacheJob: _job('submitting'),
  );

  @override
  Future<CacheJobDto> cancel(String jobId, {required bool confirmed}) async {
    cancelCalls++;
    if (cancelError) {
      throw const ApiException(code: 'cache_active_lease', message: 'fixture');
    }
    return _job('cleaned');
  }
}

class _Clock implements PlayRequestClock {
  @override
  Duration monotonicNow() => Duration.zero;

  @override
  DateTime wallNow() => DateTime.utc(2026, 7, 31, 12);
}

CacheJobDto _job(String status) => CacheJobDto.fromJson(<String, Object?>{
  'id': jobId,
  'movie_id': movieId,
  'source_id': sourceId,
  'status': status,
  'remote_percent': status == 'ready' ? 100 : 0,
  'error_code': null,
  'media_candidates': <Object?>[],
  'selected_media_ids': <Object?>[],
  'subtitles': <Object?>[],
  'ready_at': status == 'ready' ? '2026-07-31T12:00:59Z' : null,
  'expires_at': null,
  'created_at': '2026-07-31T12:00:00Z',
  'updated_at': '2026-07-31T12:00:00Z',
});

const movieId = '00000000-0000-4000-8000-000000000201';
const sourceId = '00000000-0000-4000-8000-000000000202';
const jobId = '00000000-0000-4000-8000-000000000203';

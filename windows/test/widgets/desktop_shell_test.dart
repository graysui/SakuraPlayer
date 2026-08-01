import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/core/events/snapshot_controller.dart';
import 'package:sakuraplayer_windows/features/cache/presentation/cache_badge.dart';
import 'package:sakuraplayer_windows/features/search/data/search_api.dart';
import 'package:sakuraplayer_windows/features/search/presentation/search_controller.dart';
import 'package:sakuraplayer_windows/features/search/presentation/search_overlay.dart';
import 'package:sakuraplayer_windows/widgets/shell/desktop_shell.dart';

void main() {
  testWidgets(
    'shell exposes only three navigation destinations and top tools',
    (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            home: DesktopShell(
              selectedDestination: ShellDestination.library,
              onDestinationSelected: (_) {},
              onActorSelected: (_) {},
              onCachePressed: () {},
              onSettingsPressed: () {},
              child: const Text('内容'),
            ),
          ),
        ),
      );

      expect(find.text('媒体库'), findsOneWidget);
      expect(find.text('排行榜'), findsOneWidget);
      expect(find.text('女优'), findsOneWidget);
      expect(find.text('发现'), findsNothing);
      expect(find.text('历史'), findsNothing);
      expect(find.text('订阅'), findsNothing);
      expect(find.text('下载器'), findsNothing);
      expect(find.byTooltip('全局搜索'), findsOneWidget);
      expect(find.byTooltip('缓存状态'), findsOneWidget);
      expect(find.byTooltip('管理员设置'), findsOneWidget);
      expect(
        tester
            .widget<NavigationRail>(find.byType(NavigationRail))
            .selectedIndex,
        0,
      );
    },
  );

  testWidgets('narrow window has no overflow', (tester) async {
    tester.view.physicalSize = const Size(560, 480);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      ProviderScope(
        child: MaterialApp(
          home: DesktopShell(
            selectedDestination: ShellDestination.actors,
            onDestinationSelected: (_) {},
            onActorSelected: (_) {},
            onCachePressed: () {},
            onSettingsPressed: () {},
            child: const Text('内容'),
          ),
        ),
      ),
    );

    expect(tester.takeException(), isNull);
  });

  testWidgets('capacity values never resize the cache entry', (tester) async {
    Future<Size> pumpCapacity(int queued, int running, int ready) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: CacheBadge(
              queues: QueueSnapshot(
                metadataQueued: 0,
                metadataRunning: 0,
                cacheQueued: queued,
                cacheRunning: running,
                cacheReady: ready,
              ),
              onPressed: () {},
            ),
          ),
        ),
      );
      return tester.getSize(find.byType(CacheBadge));
    }

    final zero = await pumpCapacity(0, 0, 0);
    final one = await pumpCapacity(1, 1, 1);
    final ten = await pumpCapacity(10, 10, 10);

    expect(one, zero);
    expect(ten, zero);
  });

  testWidgets('recovered snapshot updates the visible capacity values', (
    tester,
  ) async {
    final container = ProviderContainer();
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp(home: Scaffold(body: CacheBadge(onPressed: () {}))),
      ),
    );
    final originalSize = tester.getSize(find.byType(CacheBadge));

    container
        .read(snapshotStateProvider.notifier)
        .replace(
          SnapshotState.empty().copyWith(
            queues: const QueueSnapshot(
              metadataQueued: 0,
              metadataRunning: 0,
              cacheQueued: 10,
              cacheRunning: 1,
              cacheReady: 10,
            ),
          ),
        );
    await tester.pump();

    expect(
      find.descendant(
        of: find.byKey(const ValueKey('cache-queued-count')),
        matching: find.text('10'),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: find.byKey(const ValueKey('cache-running-count')),
        matching: find.text('1'),
      ),
      findsOneWidget,
    );
    expect(tester.getSize(find.byType(CacheBadge)), originalSize);
  });

  testWidgets('search groups results and failed completion has no spinner', (
    tester,
  ) async {
    final gateway = _SearchGateway();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          searchGatewayProvider.overrideWithValue(gateway),
          searchDebounceDurationProvider.overrideWithValue(Duration.zero),
        ],
        child: const MaterialApp(home: Scaffold(body: SearchOverlay())),
      ),
    );

    await tester.tap(find.byTooltip('全局搜索'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'ABC-123');
    await tester.pumpAndSettle();

    expect(find.text('影片'), findsOneWidget);
    expect(find.text('女优'), findsOneWidget);
    expect(find.text('测试影片'), findsOneWidget);
    expect(find.text('樱'), findsOneWidget);
    expect(find.text('补全失败'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsNothing);
  });

  testWidgets('actor search result closes the dialog and reports its id', (
    tester,
  ) async {
    String? selectedActorId;
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          searchGatewayProvider.overrideWithValue(_SearchGateway()),
          searchDebounceDurationProvider.overrideWithValue(Duration.zero),
        ],
        child: MaterialApp(
          home: Scaffold(
            body: SearchOverlay(
              onActorSelected: (actorId) => selectedActorId = actorId,
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.byTooltip('全局搜索'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, '樱');
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(ListTile, '樱'));
    await tester.pumpAndSettle();

    expect(selectedActorId, '00000000-0000-4000-8000-000000000002');
    expect(find.byType(Dialog), findsNothing);
  });

  testWidgets('movie search result closes the dialog and reports its id', (
    tester,
  ) async {
    String? selectedMovieId;
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          searchGatewayProvider.overrideWithValue(_SearchGateway()),
          searchDebounceDurationProvider.overrideWithValue(Duration.zero),
        ],
        child: MaterialApp(
          home: Scaffold(
            body: SearchOverlay(
              onMovieSelected: (movieId) => selectedMovieId = movieId,
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.byTooltip('全局搜索'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'ABC-123');
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(ListTile, '测试影片'));
    await tester.pumpAndSettle();

    expect(selectedMovieId, '00000000-0000-4000-8000-000000000001');
    expect(find.byType(Dialog), findsNothing);
  });
}

class _SearchGateway implements SearchGateway {
  @override
  Future<SearchResultDto> search(String query, {int limit = 10}) async {
    return SearchResultDto.fromJson(<String, Object?>{
      'movies': <Object?>[
        <String, Object?>{
          'id': '00000000-0000-4000-8000-000000000001',
          'number': 'ABC-123',
          'title': '测试影片',
          'title_original': null,
          'cover_url': null,
          'publish_date': null,
          'labels': <Object?>[],
          'favorite': false,
          'source_count': 1,
          'progress': null,
        },
      ],
      'actors': <Object?>[
        <String, Object?>{
          'id': '00000000-0000-4000-8000-000000000002',
          'display_name': '樱',
          'name_ja': null,
          'name_zh': '樱',
          'aliases': <Object?>[],
          'profile_url': null,
          'favorite': false,
        },
      ],
      'pending_metadata': <Object?>[
        <String, Object?>{
          'movie_id': '00000000-0000-4000-8000-000000000001',
          'number': 'ABC-123',
          'state': 'failed',
          'metadata_job_id': '00000000-0000-4000-8000-000000000003',
        },
      ],
    });
  }
}

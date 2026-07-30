import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/features/library/data/movies_api.dart';
import 'package:sakuraplayer_windows/features/library/presentation/movie_card.dart';
import 'package:sakuraplayer_windows/features/rankings/data/rankings_api.dart';
import 'package:sakuraplayer_windows/features/rankings/presentation/rankings_controller.dart';
import 'package:sakuraplayer_windows/features/rankings/presentation/rankings_page.dart';

void main() {
  testWidgets('four boards expose years only for TOP250', (tester) async {
    final gateway = _SequenceGateway(<Object>[
      _page(board: RankingBoard.daily),
      _page(board: RankingBoard.top250, availableYears: <int>[2026, 2025]),
      _page(
        board: RankingBoard.top250,
        year: 2025,
        availableYears: <int>[2026, 2025],
      ),
    ]);
    await _pumpPage(tester, gateway);

    for (final label in <String>['日榜', '周榜', '月榜', 'TOP250']) {
      expect(find.text(label), findsOneWidget);
    }
    expect(find.byKey(const ValueKey('ranking-year-selector')), findsNothing);

    await tester.tap(find.text('TOP250'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('ranking-year-selector')), findsOneWidget);
    expect(find.text('总榜'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('ranking-year-selector')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('2025').last);
    await tester.pumpAndSettle();

    expect(gateway.requests.last.selection.year, 2025);
    expect(gateway.requests.last.cursor, isNull);
  });

  testWidgets('rank gaps, sync time and fixed card grid stay visible', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1200, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final gateway = _SequenceGateway(<Object>[
      _page(board: RankingBoard.daily, ranks: <int>[1, 7]),
    ]);
    await _pumpPage(tester, gateway);

    expect(find.text('#1'), findsOneWidget);
    expect(find.text('#7'), findsOneWidget);
    expect(find.byType(MovieCard), findsNWidgets(2));
    expect(find.byKey(const ValueKey('ranking-synced-at')), findsOneWidget);
    final grid = tester.widget<SliverGrid>(
      find.byKey(const ValueKey('rankings-grid')),
    );
    final delegate =
        grid.gridDelegate as SliverGridDelegateWithFixedCrossAxisCount;
    expect(delegate.crossAxisCount, 5);
    expect(delegate.mainAxisExtent, 408);
  });

  testWidgets('ranking cards use the shared authenticated cover gateway', (
    tester,
  ) async {
    const coverUrl =
        '/api/v1/catalog/images/00000000-0000-4000-8000-000000000010';
    final coverGateway = _CoverGateway();
    await _pumpPage(
      tester,
      _SequenceGateway(<Object>[
        _page(board: RankingBoard.daily, coverUrl: coverUrl),
      ]),
      moviesGateway: coverGateway,
    );

    expect(coverGateway.loadedUrls, <String>[coverUrl]);
  });

  testWidgets('credential unavailable state opens settings', (tester) async {
    var settingsOpened = false;
    final gateway = _SequenceGateway(<Object>[
      _page(board: RankingBoard.daily),
      const ApiException(
        code: 'ranking_snapshot_unavailable',
        message: 'unavailable',
        statusCode: 503,
        details: <String, Object?>{'reason': 'credentials_not_configured'},
      ),
    ]);
    await _pumpPage(
      tester,
      gateway,
      onOpenSettings: () => settingsOpened = true,
    );

    expect(find.text('TOP250 尚未配置 JavDB 凭据'), findsNothing);
    final container = ProviderScope.containerOf(
      tester.element(find.byType(RankingsPage)),
    );
    await container
        .read(rankingsControllerProvider.notifier)
        .selectBoard(RankingBoard.top250);
    await tester.pumpAndSettle();
    expect(find.text('TOP250 尚未配置 JavDB 凭据'), findsOneWidget);
    await tester.tap(find.widgetWithText(FilledButton, '前往设置'));
    expect(settingsOpened, isTrue);
  });

  for (final scenario in <(String, String, String)>[
    ('credentials_invalid', 'JavDB 凭据已失效', '前往设置'),
    ('never_synced', '当前榜单尚未生成快照', '重新加载'),
    ('sync_failed', '当前榜单同步失败，暂无可用快照', '重新加载'),
  ]) {
    testWidgets('snapshot unavailable ${scenario.$1} is localized', (
      tester,
    ) async {
      final gateway = _SequenceGateway(<Object>[
        _page(board: RankingBoard.daily),
        ApiException(
          code: 'ranking_snapshot_unavailable',
          message: 'unavailable',
          statusCode: 503,
          details: <String, Object?>{'reason': scenario.$1},
        ),
      ]);
      await _pumpPage(tester, gateway);
      final container = ProviderScope.containerOf(
        tester.element(find.byType(RankingsPage)),
      );

      await container
          .read(rankingsControllerProvider.notifier)
          .selectBoard(RankingBoard.top250);
      await tester.pumpAndSettle();

      expect(find.text(scenario.$2), findsOneWidget);
      expect(find.widgetWithText(FilledButton, scenario.$3), findsOneWidget);
    });
  }

  testWidgets('empty snapshot is distinct from loading and failure', (
    tester,
  ) async {
    await _pumpPage(
      tester,
      _SequenceGateway(<Object>[
        _page(board: RankingBoard.daily, ranks: const <int>[]),
      ]),
    );
    expect(find.text('当前榜单暂无可展示影片'), findsOneWidget);
    expect(find.text('排行榜加载失败'), findsNothing);
  });

  testWidgets('ordinary initial failure exposes retry', (tester) async {
    await _pumpPage(
      tester,
      _SequenceGateway(<Object>[
        const ApiException(code: 'offline', message: 'offline'),
      ]),
    );
    expect(find.text('排行榜加载失败'), findsOneWidget);
    expect(find.text('当前榜单暂无可展示影片'), findsNothing);
    expect(find.widgetWithText(FilledButton, '重试'), findsOneWidget);
  });

  testWidgets('refresh and append failures keep the successful cards', (
    tester,
  ) async {
    final gateway = _SequenceGateway(<Object>[
      _page(board: RankingBoard.daily, nextCursor: 'cursor-2'),
      const ApiException(code: 'offline', message: 'offline'),
      const ApiException(code: 'append_failed', message: 'append failed'),
      _page(board: RankingBoard.daily, ranks: <int>[25]),
    ]);
    await _pumpPage(tester, gateway);
    expect(find.byType(MovieCard), findsOneWidget);

    await tester.tap(find.byTooltip('刷新排行榜'));
    await tester.pumpAndSettle();
    expect(find.byType(MovieCard), findsOneWidget);
    expect(find.text('刷新失败，仍显示上次快照'), findsOneWidget);

    final container = ProviderScope.containerOf(
      tester.element(find.byType(RankingsPage)),
    );
    await container.read(rankingsControllerProvider.notifier).loadMore();
    await tester.pumpAndSettle();
    await tester.drag(find.byType(CustomScrollView), const Offset(0, -1200));
    await tester.pumpAndSettle();
    expect(find.text('加载更多失败'), findsOneWidget);
    expect(find.byType(MovieCard), findsOneWidget);

    await tester.tap(find.widgetWithText(TextButton, '重试加载'));
    await tester.pumpAndSettle();
    expect(find.byType(MovieCard), findsNWidgets(2));
  });

  testWidgets('narrow page has no overflow', (tester) async {
    tester.view.physicalSize = const Size(520, 760);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final gateway = _SequenceGateway(<Object>[
      _page(board: RankingBoard.daily),
    ]);
    await _pumpPage(tester, gateway);

    expect(find.byType(MovieCard), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

Future<void> _pumpPage(
  WidgetTester tester,
  RankingsGateway gateway, {
  VoidCallback? onOpenSettings,
  MoviesGateway? moviesGateway,
}) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        rankingsGatewayProvider.overrideWithValue(gateway),
        moviesGatewayProvider.overrideWithValue(
          moviesGateway ?? _CoverGateway(),
        ),
      ],
      child: MaterialApp(
        home: Scaffold(
          body: RankingsPage(onOpenSettings: onOpenSettings ?? () {}),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

RankingPageDto _page({
  required RankingBoard board,
  int? year,
  List<int> ranks = const <int>[1],
  List<int> availableYears = const <int>[],
  String? nextCursor,
  String? coverUrl,
}) => RankingPageDto.fromJson(<String, Object?>{
  'board': board.apiValue,
  'year': year,
  'available_years': availableYears,
  'synced_at': '2026-07-30T10:30:00Z',
  'items': <Object?>[
    for (var index = 0; index < ranks.length; index++)
      <String, Object?>{
        'rank': ranks[index],
        'movie': <String, Object?>{
          'id':
              '00000000-0000-4000-8000-${(index + 1).toString().padLeft(12, '0')}',
          'number': 'RANK-${index + 1}',
          'title': '排行榜影片 ${index + 1}',
          'title_original': null,
          'cover_url': coverUrl,
          'publish_date': '2026-07-30',
          'labels': <Object?>['subtitle'],
          'favorite': false,
          'source_count': 1,
          'progress': null,
        },
      },
  ],
  'next_cursor': nextCursor,
});

class _Request {
  const _Request(this.selection, this.cursor);

  final RankingSelection selection;
  final String? cursor;
}

class _SequenceGateway implements RankingsGateway {
  _SequenceGateway(this.results);

  final List<Object> results;
  final List<_Request> requests = <_Request>[];

  @override
  Future<RankingPageDto> listRanking({
    required RankingSelection selection,
    String? cursor,
  }) async {
    requests.add(_Request(selection, cursor));
    final result = results[requests.length - 1];
    if (result is Exception) throw result;
    return result as RankingPageDto;
  }
}

class _CoverGateway implements MoviesGateway {
  final List<String> loadedUrls = <String>[];

  @override
  Future<MoviePageDto> listMovies({
    required MovieFilters filters,
    String? cursor,
  }) async => const MoviePageDto(items: <MovieSummaryDto>[], nextCursor: null);

  @override
  Future<List<int>> loadCover(String coverUrl) async {
    loadedUrls.add(coverUrl);
    return <int>[];
  }
}

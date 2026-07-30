import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/features/library/data/movies_api.dart';
import 'package:sakuraplayer_windows/features/library/presentation/library_controller.dart';
import 'package:sakuraplayer_windows/features/library/presentation/library_filters.dart';
import 'package:sakuraplayer_windows/features/library/presentation/library_page.dart';
import 'package:sakuraplayer_windows/features/library/presentation/movie_card.dart';

void main() {
  testWidgets(
    'filters keep independent category, label, favorite and size state',
    (tester) async {
      var filters = const MovieFilters();
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: StatefulBuilder(
              builder:
                  (context, setState) => SingleChildScrollView(
                    child: LibraryFilters(
                      filters: filters,
                      onChanged: (next) => setState(() => filters = next),
                    ),
                  ),
            ),
          ),
        ),
      );

      await tester.tap(find.widgetWithText(FilterChip, '中文字幕'));
      await tester.pump();
      await tester.tap(find.widgetWithText(FilterChip, '字幕'));
      await tester.pump();
      await tester.tap(find.text('仅收藏'));
      await tester.pump();
      await tester.enterText(
        find.byKey(const ValueKey('minimum-resource-size')),
        '512',
      );
      await tester.testTextInput.receiveAction(TextInputAction.done);
      await tester.pump();

      expect(filters.categories, <String>{'中文字幕'});
      expect(filters.labels, <String>{'subtitle'});
      expect(filters.favorite, isTrue);
      expect(filters.minResourceSizeMb, 512);
    },
  );

  testWidgets(
    'movie card keeps fixed poster geometry and truncates long titles',
    (tester) async {
      final movie = _movie(
        title: '这是一个非常长而且不应该改变卡片高度或覆盖播放按钮的影片标题' * 3,
        hasCover: true,
      );
      await tester.pumpWidget(
        MaterialApp(
          home: Center(
            child: SizedBox(
              width: 184,
              height: 408,
              child: MovieCard(
                movie: movie,
                coverLoader: (_) async => throw StateError('image failed'),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final aspect = tester.widget<AspectRatio>(
        find.byKey(const ValueKey('movie-poster-aspect')),
      );
      expect(aspect.aspectRatio, closeTo(2 / 3, 0.0001));
      final title = tester.widget<Text>(find.text(movie.title));
      expect(title.maxLines, 2);
      expect(title.overflow, TextOverflow.ellipsis);
      expect(find.byIcon(Icons.broken_image_outlined), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'progress button distinguishes percent, completed and unknown time',
    (tester) async {
      Future<void> pump(MovieSummaryDto movie) => tester.pumpWidget(
        MaterialApp(
          home: Center(
            child: SizedBox(
              width: 200,
              height: 408,
              child: MovieCard(movie: movie, coverLoader: (_) async => <int>[]),
            ),
          ),
        ),
      );

      await pump(
        _movie(
          progress: const PlaybackProgressDto(
            positionSeconds: 300,
            durationSeconds: 1200,
            completed: false,
            version: 1,
          ),
        ),
      );
      expect(find.text('继续播放 25%'), findsOneWidget);

      await pump(
        _movie(
          progress: const PlaybackProgressDto(
            positionSeconds: 0,
            durationSeconds: 1200,
            completed: true,
            version: 2,
          ),
        ),
      );
      expect(find.text('已看完'), findsOneWidget);

      await pump(
        _movie(
          progress: const PlaybackProgressDto(
            positionSeconds: 305,
            durationSeconds: null,
            completed: false,
            version: 3,
          ),
        ),
      );
      expect(find.text('已播放 05:05'), findsOneWidget);
    },
  );

  testWidgets('movie card body and play button both open detail', (
    tester,
  ) async {
    var opened = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: Center(
          child: SizedBox(
            width: 200,
            height: 408,
            child: MovieCard(
              movie: _movie(),
              coverLoader: (_) async => <int>[],
              onOpen: () => opened++,
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('测试影片'));
    await tester.tap(find.text('播放'));
    expect(opened, 2);
  });

  testWidgets(
    'page renders one stable card per movie and five desktop tracks',
    (tester) async {
      tester.view.physicalSize = const Size(1200, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final gateway = _SequenceGateway(<Object>[
        MoviePageDto(
          items: <MovieSummaryDto>[_movie(sourceCount: 3)],
          nextCursor: null,
        ),
      ]);
      String? openedMovie;

      await tester.pumpWidget(
        ProviderScope(
          overrides: [moviesGatewayProvider.overrideWithValue(gateway)],
          child: MaterialApp(
            home: Scaffold(
              body: LibraryPage(
                onOpenMovie: (movieId) => openedMovie = movieId,
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byType(MovieCard), findsOneWidget);
      expect(find.text('3 个来源'), findsOneWidget);
      final grid = tester.widget<SliverGrid>(
        find.byKey(const ValueKey('library-grid')),
      );
      final delegate =
          grid.gridDelegate as SliverGridDelegateWithFixedCrossAxisCount;
      expect(delegate.crossAxisCount, 5);
      expect(delegate.mainAxisExtent, 408);
      await tester.tap(find.text('测试影片'));
      expect(openedMovie, _movie().id);
    },
  );

  testWidgets('page keeps initial loading distinct from an empty result', (
    tester,
  ) async {
    final gateway = _ControlledGateway();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [moviesGatewayProvider.overrideWithValue(gateway)],
        child: const MaterialApp(home: Scaffold(body: LibraryPage())),
      ),
    );
    await tester.pump();

    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(find.text('没有符合筛选条件的影片'), findsNothing);

    gateway.complete(
      const MoviePageDto(items: <MovieSummaryDto>[], nextCursor: null),
    );
    await tester.pumpAndSettle();

    expect(find.byType(CircularProgressIndicator), findsNothing);
    expect(find.text('没有符合筛选条件的影片'), findsOneWidget);
  });

  testWidgets('initial and append failures expose the correct retry surface', (
    tester,
  ) async {
    final gateway = _SequenceGateway(<Object>[
      const ApiException(code: 'offline', message: 'offline'),
      MoviePageDto(items: <MovieSummaryDto>[_movie()], nextCursor: 'next'),
      const ApiException(code: 'append_failed', message: 'append failed'),
      MoviePageDto(
        items: <MovieSummaryDto>[_movie(number: 'DEF-456')],
        nextCursor: null,
      ),
    ]);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [moviesGatewayProvider.overrideWithValue(gateway)],
        child: const MaterialApp(home: Scaffold(body: LibraryPage())),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('媒体库加载失败'), findsOneWidget);
    await tester.tap(find.widgetWithText(FilledButton, '重试'));
    await tester.pumpAndSettle();
    expect(find.byType(MovieCard), findsOneWidget);

    final container = ProviderScope.containerOf(
      tester.element(find.byType(LibraryPage)),
    );
    if (gateway.calls == 2) {
      await container.read(libraryControllerProvider.notifier).loadMore();
    }
    await tester.pumpAndSettle();
    expect(gateway.calls, 3);
    await tester.drag(find.byType(CustomScrollView), const Offset(0, -1200));
    await tester.pumpAndSettle();
    expect(find.text('加载更多失败'), findsOneWidget);
    expect(find.byType(MovieCard), findsOneWidget);

    await tester.tap(find.widgetWithText(TextButton, '重试加载'));
    await tester.pumpAndSettle();
    expect(find.byType(MovieCard), findsNWidgets(2));
  });

  testWidgets('narrow page keeps controls and card content within bounds', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(520, 760);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final gateway = _SequenceGateway(<Object>[
      MoviePageDto(
        items: <MovieSummaryDto>[
          _movie(title: 'LongUnbrokenMovieTitleThatMustNotResizeTheGridTrack'),
        ],
        nextCursor: null,
      ),
    ]);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [moviesGatewayProvider.overrideWithValue(gateway)],
        child: const MaterialApp(home: Scaffold(body: LibraryPage())),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(MovieCard), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

MovieSummaryDto _movie({
  String number = 'ABC-123',
  String title = '测试影片',
  int sourceCount = 1,
  PlaybackProgressDto? progress,
  bool hasCover = false,
}) => MovieSummaryDto(
  id:
      number == 'ABC-123'
          ? '00000000-0000-4000-8000-000000000001'
          : '00000000-0000-4000-8000-000000000002',
  number: number,
  title: title,
  titleOriginal: null,
  coverUrl:
      hasCover
          ? '/api/v1/catalog/images/00000000-0000-4000-8000-000000000010'
          : null,
  publishDate: '2026-07-30',
  labels: const <String>['subtitle'],
  favorite: false,
  sourceCount: sourceCount,
  progress: progress,
);

class _SequenceGateway implements MoviesGateway {
  _SequenceGateway(this.results);

  final List<Object> results;
  int calls = 0;

  @override
  Future<MoviePageDto> listMovies({
    required MovieFilters filters,
    String? cursor,
  }) async {
    final result = results[calls++];
    if (result is Exception) throw result;
    return result as MoviePageDto;
  }

  @override
  Future<List<int>> loadCover(String coverUrl) async => <int>[];
}

class _ControlledGateway implements MoviesGateway {
  final _result = Completer<MoviePageDto>();

  @override
  Future<MoviePageDto> listMovies({
    required MovieFilters filters,
    String? cursor,
  }) => _result.future;

  void complete(MoviePageDto page) => _result.complete(page);

  @override
  Future<List<int>> loadCover(String coverUrl) async => <int>[];
}

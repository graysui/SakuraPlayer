import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sakuraplayer_windows/core/images/gfriends_cache.dart';
import 'package:sakuraplayer_windows/features/actors/data/actors_api.dart';
import 'package:sakuraplayer_windows/features/actors/presentation/actor_detail_page.dart';
import 'package:sakuraplayer_windows/features/actors/presentation/actors_page.dart';
import 'package:sakuraplayer_windows/features/library/data/movies_api.dart';
import 'package:sakuraplayer_windows/features/library/presentation/movie_card.dart';

void main() {
  testWidgets('list searches aliases, switches favorites and opens detail', (
    tester,
  ) async {
    final gateway = _PageGateway(
      page: ActorPageDto(
        items: <ActorSummaryDto>[
          _actor(
            aliases: const <String>['这是一个用于验证固定区域换行与省略行为的特别长权威别名', 'Sakura'],
          ),
        ],
        nextCursor: null,
      ),
      detail: _detail(),
    );
    String? opened;
    await _pump(
      tester,
      gateway: gateway,
      child: ActorsPage(onOpenActor: (actorId) => opened = actorId),
    );

    expect(find.text('女优'), findsOneWidget);
    expect(find.textContaining('特别长权威别名'), findsOneWidget);
    expect(find.text('桜'), findsOneWidget);
    expect(find.text('暂无头像'), findsOneWidget);

    await tester.enterText(find.byType(TextField), '  Sakura  ');
    await tester.pump(const Duration(milliseconds: 300));
    await tester.pumpAndSettle();
    expect(gateway.listScopes.last.normalizedQuery, 'Sakura');

    await tester.tap(find.text('收藏'));
    await tester.pumpAndSettle();
    expect(gateway.listScopes.last.favorite, isTrue);

    await tester.tap(find.byKey(const ValueKey('actor-card-$actorId')));
    expect(opened, actorId);
  });

  testWidgets('detail shows independent placeholders and related MovieCard', (
    tester,
  ) async {
    final gateway = _PageGateway(
      page: const ActorPageDto(items: <ActorSummaryDto>[], nextCursor: null),
      detail: _detail(),
    );
    String? openedMovie;
    await _pump(
      tester,
      gateway: gateway,
      child: ActorDetailPage(
        actorId: actorId,
        onOpenMovie: (movieId) => openedMovie = movieId,
      ),
    );

    expect(find.text('暂无头像'), findsOneWidget);
    expect(find.text('暂无简介'), findsOneWidget);
    expect(find.text('暂无写真'), findsOneWidget);
    expect(find.byType(MovieCard), findsOneWidget);
    expect(find.text('关联影片'), findsNWidgets(2));
    await tester.drag(find.byType(CustomScrollView), const Offset(0, -700));
    await tester.pumpAndSettle();
    await tester.tap(find.text('关联影片').last);
    expect(openedMovie, '00000000-0000-4000-8000-000000000002');
  });

  testWidgets('gallery opens a zoom viewer and moves between images', (
    tester,
  ) async {
    final gallery = <String>[_url('1.jpg'), _url('2.jpg')];
    final gateway = _PageGateway(
      page: const ActorPageDto(items: <ActorSummaryDto>[], nextCursor: null),
      detail: _detail(profileUrl: _url('profile.jpg'), gallery: gallery),
    );
    final cache = _MemoryImageCache();
    await _pump(
      tester,
      gateway: gateway,
      cache: cache,
      child: const ActorDetailPage(actorId: actorId),
    );

    await tester.tap(find.byKey(const ValueKey('gallery-thumbnail-0')));
    await tester.pumpAndSettle();
    expect(find.byType(InteractiveViewer), findsOneWidget);
    expect(find.text('1 / 2'), findsOneWidget);

    await tester.tap(find.byTooltip('下一张'));
    await tester.pumpAndSettle();
    expect(find.text('2 / 2'), findsOneWidget);
    expect(cache.loadedUrls, containsAll(gallery));
  });

  testWidgets('detail favorite is idempotent and updates the icon', (
    tester,
  ) async {
    final gateway = _PageGateway(
      page: const ActorPageDto(items: <ActorSummaryDto>[], nextCursor: null),
      detail: _detail(),
    );
    await _pump(
      tester,
      gateway: gateway,
      child: const ActorDetailPage(actorId: actorId),
    );

    await tester.tap(find.byTooltip('收藏女优'));
    await tester.pumpAndSettle();

    expect(gateway.favoriteRequests, <bool>[true]);
    expect(find.byTooltip('取消收藏'), findsOneWidget);
  });
}

const actorId = '00000000-0000-4000-8000-000000000001';

String _url(String name) =>
    'https://raw.githubusercontent.com/li-peifeng/gfriends/main/Content/Test/$name';

ActorSummaryDto _actor({
  List<String> aliases = const <String>['桜', 'Sakura'],
  String? profileUrl,
  bool favorite = false,
}) => ActorSummaryDto(
  id: actorId,
  displayName: '樱',
  nameJa: '桜',
  nameZh: '樱',
  aliases: aliases,
  profileUrl: profileUrl,
  favorite: favorite,
);

ActorDetailDto _detail({
  String? profileUrl,
  List<String> gallery = const <String>[],
}) => ActorDetailDto(
  id: actorId,
  displayName: '樱',
  nameJa: '桜',
  nameZh: '樱',
  aliases: const <String>['桜', 'Sakura'],
  profileUrl: profileUrl,
  favorite: false,
  bio: null,
  bioOriginal: null,
  galleryUrls: gallery,
  movies: <MovieSummaryDto>[
    MovieSummaryDto.fromJson(<String, Object?>{
      'id': '00000000-0000-4000-8000-000000000002',
      'number': 'ABC-123',
      'title': '关联影片',
      'title_original': null,
      'cover_url': null,
      'publish_date': '2026-07-30',
      'labels': <Object?>['subtitle'],
      'favorite': false,
      'source_count': 1,
      'progress': null,
    }),
  ],
);

Future<void> _pump(
  WidgetTester tester, {
  required ActorsGateway gateway,
  required Widget child,
  GfriendsImageCache? cache,
}) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        actorsGatewayProvider.overrideWithValue(gateway),
        gfriendsCacheProvider.overrideWithValue(cache ?? _MemoryImageCache()),
        moviesGatewayProvider.overrideWithValue(_MoviesGateway()),
      ],
      child: MaterialApp(home: Scaffold(body: child)),
    ),
  );
  await tester.pumpAndSettle();
}

class _PageGateway implements ActorsGateway {
  _PageGateway({required this.page, required this.detail});

  final ActorPageDto page;
  ActorDetailDto detail;
  final List<ActorListScope> listScopes = <ActorListScope>[];
  final List<bool> favoriteRequests = <bool>[];

  @override
  Future<ActorPageDto> listActors({
    required ActorListScope scope,
    String? cursor,
  }) async {
    listScopes.add(scope);
    return page;
  }

  @override
  Future<ActorDetailDto> getActor(String actorId) async => detail;

  @override
  Future<void> setFavorite(String actorId, {required bool enabled}) async {
    favoriteRequests.add(enabled);
    detail = detail.copyWith(favorite: enabled);
  }
}

class _MemoryImageCache implements GfriendsImageCache {
  final List<String> loadedUrls = <String>[];

  @override
  GfriendsLoadHandle load(String url) {
    loadedUrls.add(url);
    return GfriendsLoadHandle(
      bytes: Future<Uint8List>.value(
        base64Decode(
          'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
        ),
      ),
      cancel: () {},
    );
  }

  @override
  Future<void> clear() async {}

  @override
  void dispose() {}

  @override
  Future<void> prune() async {}
}

class _MoviesGateway implements MoviesGateway {
  @override
  Future<List<int>> loadCover(String coverUrl) async => <int>[];

  @override
  Future<MoviePageDto> listMovies({
    required MovieFilters filters,
    String? cursor,
  }) => throw UnimplementedError();
}

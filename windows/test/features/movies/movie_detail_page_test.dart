import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sakuraplayer_windows/features/library/data/movies_api.dart';
import 'package:sakuraplayer_windows/features/movies/data/movie_detail_api.dart';
import 'package:sakuraplayer_windows/features/movies/presentation/movie_detail_page.dart';
import 'package:sakuraplayer_windows/features/movies/presentation/source_list.dart';
import 'package:sakuraplayer_windows/features/playback/presentation/progress_controller.dart';

void main() {
  testWidgets('source list shows six states, size truth and rejected lock', (
    tester,
  ) async {
    final selected = <String>[];
    final sources = <MovieSourceDto>[
      _source(0, MovieSourceAvailability.available, resourceSizeMb: 2048),
      _source(1, MovieSourceAvailability.queued),
      _source(2, MovieSourceAvailability.running),
      _source(3, MovieSourceAvailability.ready, videoFileSizeBytes: 1073741824),
      _source(4, MovieSourceAvailability.failed),
      _source(5, MovieSourceAvailability.rejected),
    ];
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: SourceList(
              sources: sources,
              selectedSourceId: null,
              onSelected: selected.add,
            ),
          ),
        ),
      ),
    );

    for (final label in ['可缓存', '排队中', '处理中', '可播放', '上次失败', '不可用']) {
      expect(find.text(label), findsOneWidget);
    }
    expect(find.text('资源大小 2048 MiB'), findsOneWidget);
    expect(find.text('视频文件大小 1 GiB'), findsOneWidget);
    expect(find.text('资源大小未知'), findsNWidgets(4));

    await tester.tap(find.byKey(const ValueKey('source-row-0')));
    await tester.tap(find.byKey(const ValueKey('source-row-5')));
    expect(selected, <String>[_sourceId(0)]);
    expect(
      tester.getSize(find.byKey(const ValueKey('source-row-0'))).height,
      greaterThanOrEqualTo(88),
    );
  });

  testWidgets('detail requires a source and emits only its id', (tester) async {
    final gateway = _MovieGateway(_detail());
    final played = <String>[];
    String? openedActor;
    await _pumpPage(
      tester,
      gateway: gateway,
      onOpenActor: (id) => openedActor = id,
      onPlaySource: played.add,
    );

    expect(find.text('测试影片'), findsOneWidget);
    expect(find.text('继续播放 25%'), findsOneWidget);
    expect(find.text('测试厂商'), findsOneWidget);
    final playButton = tester.widget<FilledButton>(
      find.byKey(const ValueKey('movie-detail-play')),
    );
    expect(playButton.onPressed, isNull);

    await tester.ensureVisible(find.text('测试女优'));
    await tester.tap(find.text('测试女优'));
    expect(openedActor, actorId);
    await tester.ensureVisible(find.byKey(const ValueKey('source-row-0')));
    await tester.tap(find.byKey(const ValueKey('source-row-0')));
    await tester.pump();
    await tester.ensureVisible(find.byKey(const ValueKey('movie-detail-play')));
    await tester.tap(find.byKey(const ValueKey('movie-detail-play')));
    expect(played, <String>[_sourceId(0)]);
  });

  testWidgets('ready source never falls back to AVdb size', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SourceList(
            sources: <MovieSourceDto>[
              _source(0, MovieSourceAvailability.ready, resourceSizeMb: 4096),
            ],
            selectedSourceId: null,
            onSelected: (_) {},
          ),
        ),
      ),
    );

    expect(find.text('视频文件大小未知'), findsOneWidget);
    expect(find.textContaining('4096'), findsNothing);
  });

  testWidgets('detail prefers live authoritative progress', (tester) async {
    await _pumpPage(
      tester,
      gateway: _MovieGateway(_detail()),
      liveProgress: const LivePlaybackProgress(
        positionSeconds: 0,
        durationSeconds: 600,
        completed: true,
        version: 2,
      ),
    );

    expect(find.text('已看完'), findsOneWidget);
    expect(find.text('继续播放 25%'), findsNothing);
  });

  testWidgets('wide and narrow layouts keep fixed cover geometry', (
    tester,
  ) async {
    final gateway = _MovieGateway(
      _detail(
        title:
            'LongUnbrokenMovieTitleThatMustWrapWithoutCoveringActionsOrSources',
        plotImageUrls: const <String>[
          '/api/v1/catalog/images/00000000-0000-4000-8000-000000000401',
        ],
      ),
    );
    tester.view.physicalSize = const Size(1200, 1000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await _pumpPage(tester, gateway: gateway);
    expect(
      tester.getSize(find.byKey(const ValueKey('movie-detail-cover'))),
      const Size(240, 360),
    );

    tester.view.physicalSize = const Size(700, 1000);
    await tester.pump();
    expect(
      tester.getSize(find.byKey(const ValueKey('movie-detail-cover'))),
      const Size(200, 300),
    );
    expect(find.byType(GridView), findsOneWidget);
    expect(find.byType(Image), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

const movieId = '00000000-0000-4000-8000-000000000101';
const actorId = '00000000-0000-4000-8000-000000000301';

String _sourceId(int index) =>
    '00000000-0000-4000-8000-${(index + 1).toString().padLeft(12, '0')}';

MovieSourceDto _source(
  int index,
  MovieSourceAvailability availability, {
  int? resourceSizeMb,
  int? videoFileSizeBytes,
}) => MovieSourceDto(
  id: _sourceId(index),
  website: MovieSourceWebsite.sehuatang,
  externalPostId: index + 1,
  title: '来源 ${index + 1}',
  publishDate: '2026-07-30',
  category: '中文字幕',
  labels: const <String>['subtitle', 'cracked', '4k', 'censored'],
  resourceSizeMb: resourceSizeMb,
  videoFileSizeBytes: videoFileSizeBytes,
  availability: availability,
);

MovieDetailDto _detail({
  String title = '测试影片',
  List<String> plotImageUrls = const <String>[],
}) => MovieDetailDto.fromJson(<String, Object?>{
  'id': movieId,
  'number': 'ABC-123',
  'title': title,
  'title_original': 'テスト映画',
  'cover_url': null,
  'publish_date': '2026-07-30',
  'labels': <Object?>['subtitle'],
  'favorite': false,
  'source_count': 1,
  'progress': <String, Object?>{
    'position_seconds': 150,
    'duration_seconds': 600,
    'completed': false,
    'version': 1,
  },
  'release_date': '2026-07-29',
  'maker': '测试厂商',
  'series': '测试系列',
  'director': '测试导演',
  'score': 8.5,
  'description': '中文简介',
  'description_original': '日本語紹介',
  'actors': <Object?>[
    <String, Object?>{
      'id': actorId,
      'display_name': '测试女优',
      'name_ja': null,
      'name_zh': '测试女优',
      'aliases': <Object?>[],
      'profile_url': null,
      'favorite': false,
    },
  ],
  'tags': <Object?>['剧情'],
  'plot_image_urls': plotImageUrls,
  'sources': <Object?>[
    <String, Object?>{
      'id': _sourceId(0),
      'website': 'sehuatang',
      'external_post_id': 1,
      'title': '来源 1',
      'publish_date': '2026-07-30',
      'category': '中文字幕',
      'labels': <Object?>['subtitle'],
      'resource_size_mb': 1024,
      'video_file_size_bytes': null,
      'availability': 'available',
    },
  ],
});

Future<void> _pumpPage(
  WidgetTester tester, {
  required MovieDetailGateway gateway,
  ValueChanged<String>? onOpenActor,
  ValueChanged<String>? onPlaySource,
  LivePlaybackProgress? liveProgress,
}) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        movieDetailGatewayProvider.overrideWithValue(gateway),
        livePlaybackProgressProvider.overrideWith(
          () => _FixedLiveProgressNotifier(liveProgress),
        ),
      ],
      child: MaterialApp(
        home: Scaffold(
          body: MovieDetailPage(
            movieId: movieId,
            onOpenActor: onOpenActor,
            onPlaySource: onPlaySource,
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

class _FixedLiveProgressNotifier extends LivePlaybackProgressNotifier {
  _FixedLiveProgressNotifier(this.progress);

  final LivePlaybackProgress? progress;

  @override
  Map<String, LivePlaybackProgress> build() =>
      progress == null
          ? const <String, LivePlaybackProgress>{}
          : <String, LivePlaybackProgress>{movieId: progress!};
}

class _MovieGateway implements MovieDetailGateway {
  _MovieGateway(this.detail);

  MovieDetailDto detail;

  @override
  Future<MovieDetailDto> getMovie(String movieId) async => detail;

  @override
  Future<List<int>> loadCatalogImage(String imageUrl) async => base64Decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
  );

  @override
  Future<void> setFavorite(String movieId, {required bool enabled}) async {
    detail = detail.copyWith(favorite: enabled);
  }
}

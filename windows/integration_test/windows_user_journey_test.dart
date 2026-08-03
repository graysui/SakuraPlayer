import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:integration_test/integration_test.dart';
import 'package:sakuraplayer_windows/app/app.dart';
import 'package:sakuraplayer_windows/core/api/api_client.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/core/api/server_profile.dart';
import 'package:sakuraplayer_windows/core/events/snapshot_controller.dart';
import 'package:sakuraplayer_windows/core/storage/secure_store.dart';
import 'package:sakuraplayer_windows/core/storage/subtitle_cache.dart';
import 'package:sakuraplayer_windows/features/actors/data/actors_api.dart';
import 'package:sakuraplayer_windows/features/auth/domain/auth_session_state.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/auth_controller.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/login_page.dart';
import 'package:sakuraplayer_windows/features/cache/data/cache_api.dart';
import 'package:sakuraplayer_windows/features/cache/data/play_request_api.dart';
import 'package:sakuraplayer_windows/features/cache/presentation/blocking_wait_page.dart';
import 'package:sakuraplayer_windows/features/cache/presentation/play_request_controller.dart';
import 'package:sakuraplayer_windows/features/library/data/movies_api.dart'
    hide PlaybackProgressDto;
import 'package:sakuraplayer_windows/features/movies/data/movie_detail_api.dart';
import 'package:sakuraplayer_windows/features/playback/data/playback_api.dart';
import 'package:sakuraplayer_windows/features/playback/presentation/playback_engine.dart';
import 'package:sakuraplayer_windows/features/playback/presentation/player_page.dart';
import 'package:sakuraplayer_windows/features/playback/presentation/track_controller.dart';
import 'package:sakuraplayer_windows/features/rankings/data/rankings_api.dart';
import 'package:sakuraplayer_windows/features/search/data/search_api.dart';
import 'package:sakuraplayer_windows/features/settings/data/settings_api.dart';
import 'package:sakuraplayer_windows/features/settings/presentation/diagnostics_page.dart';
import 'package:sakuraplayer_windows/routes/app_router.dart';
import 'package:sakuraplayer_windows/theme/app_theme.dart';
import 'package:sakuraplayer_windows/widgets/shell/desktop_shell.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('login gate hides every authenticated route', (tester) async {
    await tester.pumpWidget(const ProviderScope(child: SakuraPlayerApp()));
    await tester.pumpAndSettle();

    expect(find.byType(LoginPage), findsOneWidget);
    expect(find.byType(DesktopShell), findsNothing);
    expect(find.byType(PlayerPage), findsNothing);
    expect(find.widgetWithText(TextField, '服务端地址'), findsOneWidget);
    expect(find.text('测试并保存地址'), findsOneWidget);
  });

  testWidgets('first connection covers bootstrap, server switch, and login', (
    tester,
  ) async {
    final memory = MemorySecureKeyValueStore();
    final subtitle = MemorySubtitleCache();
    final requests = <RequestOptions>[];
    var runtimeResetCalls = 0;
    var privateResetCalls = 0;
    final runtimeReset =
        RuntimeResetCoordinator()..register(() async {
          runtimeResetCalls++;
        });
    final privateReset =
        PrivateCacheResetCoordinator()..register(() async {
          privateResetCalls++;
        });
    final container = ProviderContainer(
      overrides: [
        secureKeyValueStoreProvider.overrideWithValue(memory),
        subtitleCacheProvider.overrideWithValue(subtitle),
        serverProbeProvider.overrideWithValue(const _FirstConnectionProbe()),
        runtimeResetProvider.overrideWithValue(runtimeReset),
        privateCacheResetProvider.overrideWithValue(privateReset),
        apiClientFactoryProvider.overrideWithValue((profile, session) {
          final dio = Dio(BaseOptions(baseUrl: '${profile.baseUri}/api/v1/'))
            ..httpClientAdapter = _AuthJourneyAdapter(requests);
          return ApiClient(dio: dio, sessionStore: session);
        }),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: LoginPage()),
      ),
    );
    await tester.enterText(
      find.widgetWithText(TextField, '服务端地址'),
      'https://first.test',
    );
    await tester.tap(find.text('测试并保存地址'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('bootstrap-token-field')), findsOneWidget);

    await tester.enterText(find.widgetWithText(TextField, '用户名'), 'admin');
    await tester.enterText(
      find.widgetWithText(TextField, '密码'),
      'first-password',
    );
    await tester.enterText(
      find.byKey(const ValueKey('bootstrap-token-field')),
      'B' * 43,
    );
    await tester.tap(find.text('创建管理员'));
    await tester.pumpAndSettle();
    expect(container.read(authControllerProvider).isAuthenticated, isTrue);
    final bootstrap = requests.singleWhere(
      (request) => request.path == 'auth/bootstrap',
    );
    expect(bootstrap.headers['X-Bootstrap-Token'], 'B' * 43);

    await container
        .read(authControllerProvider.notifier)
        .configureServer('https://second.test');
    await tester.pumpAndSettle();
    expect(container.read(authControllerProvider).isAuthenticated, isFalse);
    expect(container.read(sessionStoreProvider).accessToken, isNull);
    expect(memory.values[SecureStore.refreshTokenKey], isNull);
    expect(subtitle.cleared, isTrue);
    expect(runtimeResetCalls, 1);
    expect(privateResetCalls, 1);

    await tester.enterText(find.widgetWithText(TextField, '用户名'), 'admin');
    await tester.enterText(
      find.widgetWithText(TextField, '密码'),
      'second-password',
    );
    await tester.tap(find.text('登录'));
    await tester.pumpAndSettle();
    expect(container.read(authControllerProvider).isAuthenticated, isTrue);
    expect(
      container.read(authControllerProvider).serverBaseUri?.host,
      'second.test',
    );
    expect(requests.map((request) => request.path), contains('auth/login'));
  });

  testWidgets('wide fake backend completes the Windows user journey', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(1280, 800));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final playGateway = _FakePlayRequestGateway();
    final container = _container(playGateway: playGateway);
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const SakuraPlayerApp(),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text(_movieTitle), findsOneWidget);
    expect(find.byType(DesktopShell), findsOneWidget);

    await tester.tap(find.text('排行榜'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('rankings-page')), findsOneWidget);
    expect(find.text(_movieNumber), findsOneWidget);

    await tester.tap(find.text('女优'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('actors-page')), findsOneWidget);
    expect(find.text(_actorName), findsOneWidget);

    await tester.tap(find.byTooltip('全局搜索'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, _movieNumber);
    await tester.pump(const Duration(milliseconds: 350));
    await tester.pumpAndSettle();
    expect(find.text(_movieTitle), findsOneWidget);
    await tester.tap(find.text(_movieTitle));
    await tester.pumpAndSettle();

    expect(find.byKey(ValueKey('movie-detail-$_movieId')), findsOneWidget);
    expect(find.byKey(const ValueKey('source-row-0')), findsOneWidget);
    expect(find.byKey(const ValueKey('source-row-1')), findsOneWidget);
    await tester.ensureVisible(find.text('备用来源'));
    await tester.tap(find.text('备用来源'));
    await tester.pump();
    await tester.ensureVisible(find.byKey(const ValueKey('movie-detail-play')));
    await tester.tap(find.byKey(const ValueKey('movie-detail-play')));
    await tester.pumpAndSettle();

    expect(find.byType(BlockingWaitPage), findsOneWidget);
    expect(find.text('剩余 60 秒'), findsOneWidget);
    expect(playGateway.sourceIds, <String>[_sourceId2]);

    container.read(playRequestControllerProvider.notifier).reset();
    final snapshot = SnapshotState.empty().copyWith(
      snapshotVersion: 1,
      cacheJobs: <String, CacheJobDto>{_jobId: _job(status: 'ready')},
    );
    container.read(snapshotStateProvider.notifier).replace(snapshot);
    final router = GoRouter.of(tester.element(find.byType(BlockingWaitPage)));
    router.go(const CacheStatusRoute().location);
    await tester.pumpAndSettle();

    expect(find.byKey(ValueKey('cache-job-$_jobId')), findsOneWidget);
    expect(find.text('可播放'), findsOneWidget);
    await tester.tap(find.byTooltip('播放缓存'));
    await tester.pumpAndSettle();
    expect(find.byType(PlayerPage), findsOneWidget);
    expect(find.byKey(const ValueKey('video-surface')), findsOneWidget);
    expect(find.byTooltip('字幕'), findsOneWidget);

    router.go(const SettingsRoute().location);
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('settings-page')), findsOneWidget);
    expect(find.textContaining('验收账号'), findsOneWidget);
    await tester.tap(find.byTooltip('诊断与任务'));
    await tester.pumpAndSettle();
    expect(find.byType(DiagnosticsPage), findsOneWidget);
    expect(find.text('组件状态'), findsOneWidget);

    container.read(appThemeModeProvider.notifier).setMode(AppThemeMode.dark);
    await tester.pump();
    expect(
      tester.widget<MaterialApp>(find.byType(MaterialApp)).themeMode,
      ThemeMode.dark,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('narrow dark window recovers while optional ranking is down', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(640, 760));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final movies = _RecoveringMoviesGateway();
    final container = _container(
      movies: movies,
      rankings: const _UnavailableRankingsGateway(),
    );
    addTearDown(container.dispose);
    container.read(appThemeModeProvider.notifier).setMode(AppThemeMode.dark);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const SakuraPlayerApp(),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('媒体库加载失败'), findsOneWidget);
    await tester.tap(find.widgetWithText(FilledButton, '重试'));
    await tester.pumpAndSettle();
    expect(find.text(_movieTitle), findsOneWidget);
    expect(
      tester.widget<NavigationRail>(find.byType(NavigationRail)).extended,
      isFalse,
    );

    await tester.tap(find.byIcon(Icons.leaderboard_outlined));
    await tester.pumpAndSettle();
    expect(find.text('当前榜单尚未生成快照'), findsOneWidget);
    await tester.tap(find.byIcon(Icons.video_library_outlined));
    await tester.pumpAndSettle();
    expect(find.text(_movieTitle), findsOneWidget);
    expect(movies.calls, greaterThanOrEqualTo(2));
    expect(tester.takeException(), isNull);
  });
}

ProviderContainer _container({
  MoviesGateway? movies,
  RankingsGateway? rankings,
  _FakePlayRequestGateway? playGateway,
}) => ProviderContainer(
  overrides: [
    authSessionStateProvider.overrideWithValue(
      AuthSessionState.authenticated(
        serverBaseUri: Uri.parse('https://fixture.invalid'),
      ),
    ),
    moviesGatewayProvider.overrideWithValue(
      movies ?? const _FakeMoviesGateway(),
    ),
    rankingsGatewayProvider.overrideWithValue(
      rankings ?? const _FakeRankingsGateway(),
    ),
    actorsGatewayProvider.overrideWithValue(const _FakeActorsGateway()),
    searchGatewayProvider.overrideWithValue(const _FakeSearchGateway()),
    movieDetailGatewayProvider.overrideWithValue(
      const _FakeMovieDetailGateway(),
    ),
    playRequestGatewayProvider.overrideWithValue(
      playGateway ?? _FakePlayRequestGateway(),
    ),
    playRequestClockProvider.overrideWithValue(const _FakeClock()),
    cacheGatewayProvider.overrideWithValue(const _FakeCacheGateway()),
    playbackGatewayProvider.overrideWithValue(const _FakePlaybackGateway()),
    playbackEngineFactoryProvider.overrideWithValue(_FakePlaybackEngine.new),
    settingsGatewayProvider.overrideWithValue(const _FakeSettingsGateway()),
  ],
);

const _movieId = '00000000-0000-4000-8000-000000000101';
const _sourceId1 = '00000000-0000-4000-8000-000000000102';
const _sourceId2 = '00000000-0000-4000-8000-000000000103';
const _jobId = '00000000-0000-4000-8000-000000000104';
const _mediaId = '00000000-0000-4000-8000-000000000105';
const _candidateId = '00000000-0000-4000-8000-000000000106';
const _sessionId = '00000000-0000-4000-8000-000000000107';
const _subtitleId = '00000000-0000-4000-8000-000000000108';
const _actorId = '00000000-0000-4000-8000-000000000109';
const _movieNumber = 'FAKE-213';
const _movieTitle = '离线全旅程影片';
const _actorName = '验收女优';

const _movie = MovieSummaryDto(
  id: _movieId,
  number: _movieNumber,
  title: _movieTitle,
  titleOriginal: null,
  coverUrl: null,
  publishDate: '2026-07-31',
  labels: <String>['subtitle'],
  favorite: false,
  sourceCount: 2,
  progress: null,
);

const _actor = ActorSummaryDto(
  id: _actorId,
  displayName: _actorName,
  nameJa: null,
  nameZh: _actorName,
  aliases: <String>['Sakura'],
  profileUrl: null,
  favorite: false,
);

class _FirstConnectionProbe implements ServerProbe {
  const _FirstConnectionProbe();

  @override
  Future<BootstrapStatus> test(ServerProfile profile) async => BootstrapStatus(
    initialized: profile.baseUri.host == 'second.test',
    apiVersion: 1,
  );
}

class _AuthJourneyAdapter implements HttpClientAdapter {
  const _AuthJourneyAdapter(this.requests);

  final List<RequestOptions> requests;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options);
    switch (options.path) {
      case 'auth/bootstrap':
      case 'auth/login':
        return ResponseBody.fromString(
          jsonEncode(<String, Object?>{
            'access_token': 'journey-access-token',
            'refresh_token': 'journey-refresh-token',
            'token_type': 'Bearer',
            'access_expires_at': '2027-08-01T00:00:00Z',
            'refresh_expires_at': '2027-09-01T00:00:00Z',
          }),
          200,
          headers: <String, List<String>>{
            Headers.contentTypeHeader: <String>['application/json'],
          },
        );
      case 'auth/logout':
        return ResponseBody.fromString('', 204);
      default:
        throw StateError('unexpected auth journey request ${options.path}');
    }
  }

  @override
  void close({bool force = false}) {}
}

class _FakeMoviesGateway implements MoviesGateway {
  const _FakeMoviesGateway();
  @override
  Future<MoviePageDto> listMovies({
    required MovieFilters filters,
    String? cursor,
  }) async =>
      const MoviePageDto(items: <MovieSummaryDto>[_movie], nextCursor: null);
  @override
  Future<List<int>> loadCover(String coverUrl) async => const <int>[];
}

class _RecoveringMoviesGateway implements MoviesGateway {
  int calls = 0;
  @override
  Future<MoviePageDto> listMovies({
    required MovieFilters filters,
    String? cursor,
  }) async {
    calls++;
    if (calls == 1) {
      throw const ApiException(code: 'offline', message: 'offline');
    }
    return const MoviePageDto(
      items: <MovieSummaryDto>[_movie],
      nextCursor: null,
    );
  }

  @override
  Future<List<int>> loadCover(String coverUrl) async => const <int>[];
}

class _FakeRankingsGateway implements RankingsGateway {
  const _FakeRankingsGateway();
  @override
  Future<RankingPageDto> listRanking({
    required RankingSelection selection,
    String? cursor,
  }) async => RankingPageDto(
    board: selection.board,
    year: selection.year,
    availableYears: const <int>[],
    syncedAt: DateTime.utc(2026, 7, 31),
    items: const <RankingItemDto>[RankingItemDto(rank: 1, movie: _movie)],
    nextCursor: null,
  );
}

class _UnavailableRankingsGateway implements RankingsGateway {
  const _UnavailableRankingsGateway();
  @override
  Future<RankingPageDto> listRanking({
    required RankingSelection selection,
    String? cursor,
  }) =>
      throw const ApiException(
        statusCode: 503,
        code: 'ranking_snapshot_unavailable',
        message: 'unavailable',
        details: <String, Object?>{'reason': 'never_synced'},
      );
}

class _FakeActorsGateway implements ActorsGateway {
  const _FakeActorsGateway();
  @override
  Future<ActorPageDto> listActors({
    required ActorListScope scope,
    String? cursor,
  }) async =>
      const ActorPageDto(items: <ActorSummaryDto>[_actor], nextCursor: null);
  @override
  Future<ActorDetailDto> getActor(String actorId) async => const ActorDetailDto(
    id: _actorId,
    displayName: _actorName,
    nameJa: null,
    nameZh: _actorName,
    aliases: <String>['Sakura'],
    profileUrl: null,
    favorite: false,
    bio: '离线验收简介',
    bioOriginal: null,
    galleryUrls: <String>[],
    movies: <MovieSummaryDto>[_movie],
  );
  @override
  Future<void> setFavorite(String actorId, {required bool enabled}) async {}
}

class _FakeSearchGateway implements SearchGateway {
  const _FakeSearchGateway();
  @override
  Future<SearchResultDto> search(String query, {int limit = 10}) async =>
      const SearchResultDto(
        movies: <MovieSummaryDto>[_movie],
        actors: <ActorSummaryDto>[_actor],
        pendingMetadata: <PendingMetadataDto>[],
      );
}

class _FakeMovieDetailGateway implements MovieDetailGateway {
  const _FakeMovieDetailGateway();
  @override
  Future<MovieDetailDto> getMovie(String movieId) async => const MovieDetailDto(
    id: _movieId,
    number: _movieNumber,
    title: _movieTitle,
    titleOriginal: null,
    coverUrl: null,
    publishDate: '2026-07-31',
    labels: <String>['subtitle'],
    favorite: false,
    sourceCount: 2,
    progress: null,
    releaseDate: '2026-07-31',
    maker: 'Fake Studio',
    series: null,
    director: null,
    score: 8,
    description: '不访问网络的验收数据',
    descriptionOriginal: null,
    actors: <ActorSummaryDto>[_actor],
    tags: <String>['验收'],
    plotImageUrls: <String>[],
    sources: <MovieSourceDto>[
      MovieSourceDto(
        id: _sourceId1,
        website: MovieSourceWebsite.sehuatang,
        externalPostId: 21301,
        title: '首选来源',
        publishDate: '2026-07-31',
        category: '中文字幕',
        labels: <String>['subtitle'],
        resourceSizeMb: 1024,
        videoFileSizeBytes: null,
        availability: MovieSourceAvailability.available,
      ),
      MovieSourceDto(
        id: _sourceId2,
        website: MovieSourceWebsite.x1080x,
        externalPostId: 21302,
        title: '备用来源',
        publishDate: '2026-07-31',
        category: '有码',
        labels: <String>['4k'],
        resourceSizeMb: 2048,
        videoFileSizeBytes: null,
        availability: MovieSourceAvailability.available,
      ),
    ],
  );
  @override
  Future<List<int>> loadCatalogImage(String imageUrl) async => const <int>[];
  @override
  Future<MetadataRescrapeResult> rescrapeMovie(String movieId) async =>
      const MetadataRescrapeResult(
        jobId: '00000000-0000-4000-8000-000000000501',
        state: MetadataRescrapeState.queued,
        created: true,
      );
  @override
  Future<void> setFavorite(String movieId, {required bool enabled}) async {}
}

class _FakePlayRequestGateway implements PlayRequestGateway {
  final sourceIds = <String>[];
  @override
  Future<PlayRequestResultDto> request({
    required String movieId,
    required String sourceId,
    required String idempotencyKey,
  }) async {
    sourceIds.add(sourceId);
    return PlayRequestResultDto(
      disposition: PlayDisposition.started,
      waitDeadline: DateTime.utc(2026, 7, 31, 12, 1),
      cacheJob: _job(status: 'submitting'),
    );
  }

  @override
  Future<CacheJobDto> cancel(String jobId, {required bool confirmed}) async =>
      _job(status: 'cleaned');
}

class _FakeClock implements PlayRequestClock {
  const _FakeClock();
  @override
  Duration monotonicNow() => Duration.zero;
  @override
  DateTime wallNow() => DateTime.utc(2026, 7, 31, 12);
}

class _FakeCacheGateway implements CacheGateway {
  const _FakeCacheGateway();
  @override
  Future<CacheJobPageDto> listJobs({
    Set<String> statuses = const <String>{},
    String? cursor,
  }) async => CacheJobPageDto(
    items: <CacheJobDto>[_job(status: 'ready')],
    capacity: const CacheCapacityDto(
      running: 0,
      runningLimit: 2,
      queued: 0,
      queuedLimit: 10,
      ready: 1,
      readyLimit: 20,
    ),
    nextCursor: null,
  );
  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError(invocation.memberName.toString());
}

CacheJobDto _job({required String status}) => CacheJobDto(
  id: _jobId,
  movieId: _movieId,
  sourceId: _sourceId2,
  status: status,
  remotePercent: status == 'ready' ? 100 : 25,
  errorCode: null,
  mediaCandidates: const <RemoteMediaDto>[],
  selectedMediaIds: status == 'ready' ? const <String>[_mediaId] : const [],
  subtitles: const <SubtitleOptionDto>[
    SubtitleOptionDto(
      id: _subtitleId,
      mediaId: _mediaId,
      name: '验收字幕.srt',
      format: 'srt',
      language: 'zh-CN',
      selectedByDefault: false,
    ),
  ],
  readyAt: status == 'ready' ? DateTime.utc(2026, 7, 31, 12) : null,
  expiresAt: status == 'ready' ? DateTime.utc(2026, 8, 1, 12) : null,
  createdAt: DateTime.utc(2026, 7, 31, 12),
  updatedAt: DateTime.utc(2026, 7, 31, 12),
);

class _FakePlaybackGateway
    implements
        PlaybackGateway,
        SubtitleDownloadGateway,
        PlaybackProgressGateway {
  const _FakePlaybackGateway();
  @override
  Future<PlaybackManifestDto> createSession({
    required String cacheJobId,
    required String mediaId,
    required PlaybackMode mode,
  }) async => PlaybackManifestDto(
    sessionId: _sessionId,
    cacheJobId: cacheJobId,
    mode: mode,
    streamUri: Uri.parse(
      'https://fixture.invalid/api/v1/playback/streams/$_sessionId',
    ),
    expiresAt: DateTime.utc(2026, 8, 1),
    subtitleCacheExpiresAt: DateTime.utc(2026, 8, 1),
    mediaQueue: <PlaybackQueueItemDto>[
      PlaybackQueueItemDto(
        sessionId: _sessionId,
        media: const RemoteMediaDto(
          id: _mediaId,
          candidateId: _candidateId,
          name: 'journey.mp4',
          sizeBytes: 1024,
          durationSeconds: 100,
          sequenceNo: 0,
          isValid: true,
        ),
        streamUri: Uri.parse(
          'https://fixture.invalid/api/v1/playback/streams/$_sessionId',
        ),
      ),
    ],
    subtitles: const <SubtitleOptionDto>[
      SubtitleOptionDto(
        id: _subtitleId,
        mediaId: _mediaId,
        name: '验收字幕.srt',
        format: 'srt',
        language: 'zh-CN',
        selectedByDefault: false,
      ),
    ],
    progress: const PlaybackProgressDto(
      positionSeconds: 0,
      durationSeconds: 100,
      completed: false,
      version: 0,
    ),
  );
  @override
  Future<List<int>> downloadSubtitle({
    required String playbackSessionId,
    required String subtitleId,
  }) async => '1\n00:00:00,000 --> 00:00:01,000\nFake'.codeUnits;
  @override
  Future<PlaybackHeartbeatDto> heartbeat({
    required String playbackSessionId,
    required double positionSeconds,
    required double? durationSeconds,
    required int version,
    required bool playing,
  }) async => PlaybackHeartbeatDto(
    leaseExpiresAt: playing ? DateTime.utc(2026, 8, 1) : null,
    progress: PlaybackProgressDto(
      positionSeconds: positionSeconds,
      durationSeconds: durationSeconds,
      completed:
          durationSeconds != null && positionSeconds / durationSeconds >= .95,
      version: version + 1,
    ),
  );
  @override
  Future<PlaybackProgressDto> updateProgress({
    required String movieId,
    required double positionSeconds,
    required double? durationSeconds,
    required int version,
  }) async => PlaybackProgressDto(
    positionSeconds: positionSeconds,
    durationSeconds: durationSeconds,
    completed:
        durationSeconds != null && positionSeconds / durationSeconds >= .95,
    version: version + 1,
  );
}

class _FakePlaybackEngine implements PlaybackEngine {
  @override
  Stream<bool> get playingStream => const Stream<bool>.empty();
  @override
  Stream<bool> get completedStream => const Stream<bool>.empty();
  @override
  Stream<bool> get bufferingStream => const Stream<bool>.empty();
  @override
  Stream<Duration> get positionStream => const Stream<Duration>.empty();
  @override
  Stream<Duration> get durationStream => const Stream<Duration>.empty();
  @override
  Stream<String> get errorStream => const Stream<String>.empty();
  @override
  Stream<EmbeddedTrackCatalog> get trackCatalogStream =>
      const Stream<EmbeddedTrackCatalog>.empty();
  @override
  Stream<EmbeddedTrackSelection> get trackSelectionStream =>
      const Stream<EmbeddedTrackSelection>.empty();
  @override
  Widget buildVideoSurface() => const ColoredBox(color: Colors.black);
  @override
  Future<void> open(PlaybackManifestDto manifest, String mediaId) async {}
  @override
  Future<void> play() async {}
  @override
  Future<void> pause() async {}
  @override
  Future<void> seek(Duration target) async {}
  @override
  Future<void> setRate(double rate) async {}
  @override
  Future<void> selectAudioTrack(String id) async {}
  @override
  Future<void> selectEmbeddedSubtitleTrack(String? id) async {}
  @override
  Future<void> setExternalSubtitle(
    Uri uri, {
    required String title,
    String? language,
  }) async {}
  @override
  Future<void> toggleFullscreen() async {}
  @override
  Future<void> dispose() async {}
}

class _FakeSettingsGateway implements SettingsGateway {
  const _FakeSettingsGateway();
  @override
  Future<SettingsDto> getSettings() async => const SettingsDto(
    cacheTtlHours: 24,
    readyCacheLimit: 20,
    metadataConcurrency: 3,
    metadataTimeoutSeconds: 600,
    javdb: JavdbSettingsDto(
      configured: false,
      status: 'not_configured',
      lastCheckedAt: null,
      lastErrorCode: null,
      username: null,
      passwordConfigured: false,
      version: 0,
    ),
    ai: AiSettingsDto(
      configured: false,
      status: 'not_configured',
      lastCheckedAt: null,
      lastErrorCode: null,
      baseUrl: null,
      model: null,
      timeoutSeconds: null,
      apiKeyConfigured: false,
      version: 0,
    ),
    providers: <String, ProviderStateDto>{},
    incrementalSync: SyncRunStateDto(
      status: 'never',
      lastSuccessfulAt: null,
      nextScheduledAt: null,
      lastErrorCode: null,
    ),
    fullSync: SyncRunStateDto(
      status: 'never',
      lastSuccessfulAt: null,
      nextScheduledAt: null,
      lastErrorCode: null,
    ),
  );
  @override
  Future<Cloud115BindingDto> getBinding() async => const Cloud115BindingDto(
    bound: true,
    status: 'active',
    displayName: '验收账号',
    cacheRootReady: true,
    lastVerifiedAt: null,
  );
  @override
  Future<DiagnosticsDto> getDiagnostics() async => DiagnosticsDto(
    generatedAt: DateTime.utc(2026, 7, 31),
    components: <ComponentDiagnosticDto>[
      ComponentDiagnosticDto(
        component: 'api',
        status: 'healthy',
        errorCode: null,
        checkedAt: DateTime.utc(2026, 7, 31),
      ),
    ],
    queues: const QueueSnapshot(
      metadataQueued: 0,
      metadataRunning: 0,
      cacheQueued: 0,
      cacheRunning: 0,
      cacheReady: 1,
    ),
    metadataProgress: const MetadataProgressDto(
      total: 0,
      queued: 0,
      running: 0,
      completed: 0,
      failed: 0,
      finished: 0,
      currentNumbers: <String>[],
    ),
    recentFailures: const <FailureDiagnosticDto>[],
    connectionTests: const <ConnectionTestDto>[],
  );
  @override
  Future<MetadataJobPageDto> listMetadataJobs({String? cursor}) async =>
      const MetadataJobPageDto(items: <MetadataJobDto>[], nextCursor: null);
  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError(invocation.memberName.toString());
}

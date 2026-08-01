import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:sakuraplayer_windows/app/app.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/core/events/snapshot_controller.dart';
import 'package:sakuraplayer_windows/features/actors/data/actors_api.dart';
import 'package:sakuraplayer_windows/features/actors/presentation/actor_detail_page.dart';
import 'package:sakuraplayer_windows/features/auth/domain/auth_session_state.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/auth_controller.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/login_page.dart';
import 'package:sakuraplayer_windows/features/cache/data/play_request_api.dart';
import 'package:sakuraplayer_windows/features/cache/presentation/blocking_wait_page.dart';
import 'package:sakuraplayer_windows/features/cache/presentation/play_request_controller.dart';
import 'package:sakuraplayer_windows/features/library/data/movies_api.dart'
    hide PlaybackProgressDto;
import 'package:sakuraplayer_windows/features/movies/data/movie_detail_api.dart';
import 'package:sakuraplayer_windows/features/movies/presentation/movie_detail_page.dart';
import 'package:sakuraplayer_windows/features/playback/data/playback_api.dart';
import 'package:sakuraplayer_windows/features/playback/presentation/playback_engine.dart';
import 'package:sakuraplayer_windows/features/playback/presentation/player_page.dart';
import 'package:sakuraplayer_windows/features/playback/presentation/track_controller.dart';
import 'package:sakuraplayer_windows/features/rankings/data/rankings_api.dart';
import 'package:sakuraplayer_windows/features/settings/data/settings_api.dart';
import 'package:sakuraplayer_windows/features/settings/presentation/diagnostics_page.dart';
import 'package:sakuraplayer_windows/routes/app_router.dart';
import 'package:sakuraplayer_windows/theme/app_theme.dart';
import 'package:sakuraplayer_windows/theme/player_theme.dart';
import 'package:sakuraplayer_windows/widgets/shell/desktop_shell.dart';

void main() {
  testWidgets('unauthenticated session only reaches login', (tester) async {
    await tester.pumpWidget(const ProviderScope(child: SakuraPlayerApp()));
    await tester.pumpAndSettle();

    expect(find.byType(LoginPage), findsOneWidget);
    expect(find.byType(DesktopShell), findsNothing);
    expect(find.byType(PlayerPage), findsNothing);
  });

  testWidgets('login route takes precedence over a stale wait state', (
    tester,
  ) async {
    final container = ProviderContainer(
      overrides: [
        playRequestGatewayProvider.overrideWithValue(_WaitingPlayGateway()),
        playRequestClockProvider.overrideWithValue(const _RouteClock()),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const SakuraPlayerApp(),
      ),
    );
    await tester.pumpAndSettle();
    await container
        .read(playRequestControllerProvider.notifier)
        .submit(movieId: _movieId, sourceId: _sourceId);
    final router = GoRouter.of(tester.element(find.byType(LoginPage)));
    router.go(const LoginRoute().location);
    await tester.pumpAndSettle();

    expect(find.byType(LoginPage), findsOneWidget);
    expect(find.byType(BlockingWaitPage), findsNothing);
    container.read(playRequestControllerProvider.notifier).reset();
  });

  testWidgets('authenticated session enters desktop shell', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionStateProvider.overrideWithValue(
            AuthSessionState.authenticated(
              serverBaseUri: Uri.parse('https://server.test'),
            ),
          ),
          moviesGatewayProvider.overrideWithValue(const _EmptyMoviesGateway()),
          playbackGatewayProvider.overrideWithValue(_RoutePlaybackGateway()),
          playbackEngineFactoryProvider.overrideWithValue(
            () => _RoutePlaybackEngine(),
          ),
          rankingsGatewayProvider.overrideWithValue(
            const _EmptyRankingsGateway(),
          ),
        ],
        child: const SakuraPlayerApp(),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(DesktopShell), findsOneWidget);
    expect(find.byType(LoginPage), findsNothing);

    await tester.tap(find.text('排行榜'));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('rankings-page')), findsOneWidget);
    expect(
      tester.widget<NavigationRail>(find.byType(NavigationRail)).selectedIndex,
      1,
    );
  });

  testWidgets('authenticated session opens the dark in-app player', (
    tester,
  ) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionStateProvider.overrideWithValue(
            AuthSessionState.authenticated(
              serverBaseUri: Uri.parse('https://server.test'),
            ),
          ),
          moviesGatewayProvider.overrideWithValue(const _EmptyMoviesGateway()),
          playbackGatewayProvider.overrideWithValue(_RoutePlaybackGateway()),
          playbackEngineFactoryProvider.overrideWithValue(
            () => _RoutePlaybackEngine(),
          ),
        ],
        child: const SakuraPlayerApp(),
      ),
    );
    await tester.pumpAndSettle();

    GoRouter.of(
      tester.element(find.byType(DesktopShell)),
    ).go(FullscreenPlayerRoute(_jobId, _mediaId).location);
    await tester.pumpAndSettle();

    expect(find.byType(PlayerPage), findsOneWidget);
    expect(find.byKey(const ValueKey('video-surface')), findsOneWidget);
    expect(
      Theme.of(
        tester.element(find.byKey(const ValueKey('video-surface'))),
      ).brightness,
      Brightness.dark,
    );
  });

  testWidgets('actor detail typed route stays inside the actors shell', (
    tester,
  ) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionStateProvider.overrideWithValue(
            AuthSessionState.authenticated(
              serverBaseUri: Uri.parse('https://server.test'),
            ),
          ),
          moviesGatewayProvider.overrideWithValue(const _EmptyMoviesGateway()),
          actorsGatewayProvider.overrideWithValue(const _ActorsGateway()),
        ],
        child: const SakuraPlayerApp(),
      ),
    );
    await tester.pumpAndSettle();

    final router = GoRouter.of(tester.element(find.byType(DesktopShell)));
    router.go(ActorDetailRoute(_actorId).location);
    await tester.pumpAndSettle();

    expect(find.byType(ActorDetailPage), findsOneWidget);
    expect(find.text('测试女优'), findsOneWidget);
    expect(
      tester.widget<NavigationRail>(find.byType(NavigationRail)).selectedIndex,
      ShellDestination.actors.index,
    );

    router.go('/app/actors/not-an-actor-id');
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('actors-page')), findsOneWidget);
    expect(find.byType(ActorDetailPage), findsNothing);
  });

  testWidgets('movie detail typed route stays inside the library shell', (
    tester,
  ) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionStateProvider.overrideWithValue(
            AuthSessionState.authenticated(
              serverBaseUri: Uri.parse('https://server.test'),
            ),
          ),
          moviesGatewayProvider.overrideWithValue(const _EmptyMoviesGateway()),
          movieDetailGatewayProvider.overrideWithValue(
            const _MovieDetailGateway(),
          ),
        ],
        child: const SakuraPlayerApp(),
      ),
    );
    await tester.pumpAndSettle();

    final router = GoRouter.of(tester.element(find.byType(DesktopShell)));
    router.go(MovieDetailRoute(_movieId).location);
    await tester.pumpAndSettle();

    expect(find.byType(MovieDetailPage), findsOneWidget);
    expect(find.text('路由影片'), findsOneWidget);
    expect(
      tester.widget<NavigationRail>(find.byType(NavigationRail)).selectedIndex,
      ShellDestination.library.index,
    );

    router.go('/app/movies/not-a-movie-id');
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('library-page')), findsOneWidget);
    expect(find.byType(MovieDetailPage), findsNothing);
  });

  testWidgets('selected source opens guarded blocking wait route', (
    tester,
  ) async {
    final playGateway = _WaitingPlayGateway();
    final container = ProviderContainer(
      overrides: [
        authSessionStateProvider.overrideWithValue(
          AuthSessionState.authenticated(
            serverBaseUri: Uri.parse('https://server.test'),
          ),
        ),
        moviesGatewayProvider.overrideWithValue(const _EmptyMoviesGateway()),
        movieDetailGatewayProvider.overrideWithValue(
          const _MovieDetailGateway(),
        ),
        playRequestGatewayProvider.overrideWithValue(playGateway),
        playRequestClockProvider.overrideWithValue(const _RouteClock()),
        playbackGatewayProvider.overrideWithValue(_RoutePlaybackGateway()),
        playbackEngineFactoryProvider.overrideWithValue(
          () => _RoutePlaybackEngine(),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const SakuraPlayerApp(),
      ),
    );
    await tester.pumpAndSettle();
    final router = GoRouter.of(tester.element(find.byType(DesktopShell)));
    router.go(MovieDetailRoute(_movieId).location);
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.text('路由来源'));
    await tester.pump();
    await tester.tap(find.text('路由来源'));
    await tester.pump();
    await tester.ensureVisible(find.byKey(const ValueKey('movie-detail-play')));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('movie-detail-play')));
    await tester.pumpAndSettle();

    expect(find.byType(BlockingWaitPage), findsOneWidget);
    expect(find.byType(DesktopShell), findsNothing);
    expect(playGateway.movieIds, <String>[_movieId]);
    expect(playGateway.sourceIds, <String>[_sourceId]);

    router.go(const SettingsRoute().location);
    await tester.pumpAndSettle();
    expect(find.byType(BlockingWaitPage), findsOneWidget);
    container.read(playRequestControllerProvider.notifier).reset();
    await tester.pump();
  });

  testWidgets('ready arriving before wait route redirects to player', (
    tester,
  ) async {
    final playGateway = _WaitingPlayGateway();
    final container = ProviderContainer(
      overrides: [
        authSessionStateProvider.overrideWithValue(
          AuthSessionState.authenticated(
            serverBaseUri: Uri.parse('https://server.test'),
          ),
        ),
        moviesGatewayProvider.overrideWithValue(const _EmptyMoviesGateway()),
        playRequestGatewayProvider.overrideWithValue(playGateway),
        playRequestClockProvider.overrideWithValue(const _RouteClock()),
        playbackGatewayProvider.overrideWithValue(_RoutePlaybackGateway()),
        playbackEngineFactoryProvider.overrideWithValue(
          () => _RoutePlaybackEngine(),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const SakuraPlayerApp(),
      ),
    );
    await tester.pumpAndSettle();
    await container
        .read(playRequestControllerProvider.notifier)
        .submit(movieId: _movieId, sourceId: _sourceId);
    container
        .read(snapshotStateProvider.notifier)
        .replace(
          SnapshotState.empty().copyWith(
            snapshotVersion: 1,
            cacheJobs: <String, CacheJobDto>{_jobId: _routeJob('ready')},
          ),
        );

    final router = GoRouter.of(tester.element(find.byType(DesktopShell)));
    router.go(const BlockingWaitRoute().location);
    await tester.pumpAndSettle();

    expect(find.byType(PlayerPage), findsOneWidget);
    expect(find.byType(BlockingWaitPage), findsNothing);
    container.read(playRequestControllerProvider.notifier).reset();
  });

  testWidgets('diagnostics typed route stays inside the settings shell', (
    tester,
  ) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionStateProvider.overrideWithValue(
            AuthSessionState.authenticated(
              serverBaseUri: Uri.parse('https://server.test'),
            ),
          ),
          moviesGatewayProvider.overrideWithValue(const _EmptyMoviesGateway()),
          settingsGatewayProvider.overrideWithValue(
            const _RouteSettingsGateway(),
          ),
        ],
        child: const SakuraPlayerApp(),
      ),
    );
    await tester.pumpAndSettle();
    final router = GoRouter.of(tester.element(find.byType(DesktopShell)));
    router.go(const SettingsDiagnosticsRoute().location);
    await tester.pumpAndSettle();

    expect(find.byType(DiagnosticsPage), findsOneWidget);
    expect(find.byType(DesktopShell), findsOneWidget);
    expect(find.text('组件状态'), findsOneWidget);
  });

  testWidgets('theme controller supports system light and dark', (
    tester,
  ) async {
    final container = ProviderContainer();
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const SakuraPlayerApp(),
      ),
    );
    await tester.pumpAndSettle();

    expect(_materialApp(tester).themeMode, ThemeMode.system);

    container.read(appThemeModeProvider.notifier).setMode(AppThemeMode.light);
    await tester.pump();
    expect(_materialApp(tester).themeMode, ThemeMode.light);

    container.read(appThemeModeProvider.notifier).setMode(AppThemeMode.dark);
    await tester.pump();
    expect(_materialApp(tester).themeMode, ThemeMode.dark);
  });

  test('player theme remains dark for every app theme', () {
    expect(SakuraPlayerTheme.dark.brightness, Brightness.dark);
    for (final mode in AppThemeMode.values) {
      expect(mode.materialThemeMode, isA<ThemeMode>());
      expect(SakuraPlayerTheme.dark.brightness, Brightness.dark);
    }
  });

  test('route surface has no age gate or external player', () {
    expect(appRouteLocations, {
      '/login',
      '/app/library',
      '/app/rankings',
      '/app/actors',
      '/app/actors/:actor_id',
      '/app/movies/:movie_id',
      '/app/cache',
      '/app/settings',
      '/app/settings/diagnostics',
      '/wait',
      '/player/:cache_job_id/:media_id',
    });
    expect(appRouteLocations.any((path) => path.contains('age')), isFalse);
    expect(appRouteLocations.any((path) => path.contains('external')), isFalse);
    expect(() => ActorDetailRoute('not-an-actor-id'), throwsArgumentError);
    expect(() => MovieDetailRoute('not-a-movie-id'), throwsArgumentError);
    expect(
      () => FullscreenPlayerRoute('not-a-job-id', _mediaId),
      throwsArgumentError,
    );
    expect(
      const SettingsDiagnosticsRoute().location,
      '/app/settings/diagnostics',
    );
  });

  test('project contains only the Windows platform runner', () {
    expect(Directory('windows').existsSync(), isTrue);
    for (final platform in ['android', 'ios', 'linux', 'macos', 'web']) {
      expect(
        Directory(platform).existsSync(),
        isFalse,
        reason: '$platform platform directory must not exist',
      );
    }
  });
}

MaterialApp _materialApp(WidgetTester tester) {
  return tester.widget<MaterialApp>(find.byType(MaterialApp));
}

class _EmptyMoviesGateway implements MoviesGateway {
  const _EmptyMoviesGateway();

  @override
  Future<MoviePageDto> listMovies({
    required MovieFilters filters,
    String? cursor,
  }) async => const MoviePageDto(items: <MovieSummaryDto>[], nextCursor: null);

  @override
  Future<List<int>> loadCover(String coverUrl) async => <int>[];
}

class _EmptyRankingsGateway implements RankingsGateway {
  const _EmptyRankingsGateway();

  @override
  Future<RankingPageDto> listRanking({
    required RankingSelection selection,
    String? cursor,
  }) async => RankingPageDto(
    board: selection.board,
    year: selection.year,
    availableYears: const <int>[],
    syncedAt: DateTime.utc(2026, 7, 30),
    items: const <RankingItemDto>[],
    nextCursor: null,
  );
}

class _RouteSettingsGateway implements SettingsGateway {
  const _RouteSettingsGateway();

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
    bound: false,
    status: 'unbound',
    displayName: null,
    cacheRootReady: false,
    lastVerifiedAt: null,
  );

  @override
  Future<DiagnosticsDto> getDiagnostics() async => DiagnosticsDto(
    generatedAt: DateTime.utc(2026, 7, 30),
    components: <ComponentDiagnosticDto>[
      ComponentDiagnosticDto(
        component: 'api',
        status: 'healthy',
        errorCode: null,
        checkedAt: DateTime.utc(2026, 7, 30),
      ),
    ],
    queues: const QueueSnapshot(
      metadataQueued: 0,
      metadataRunning: 0,
      cacheQueued: 0,
      cacheRunning: 0,
      cacheReady: 0,
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

const _actorId = '00000000-0000-4000-8000-000000000010';
const _movieId = '00000000-0000-4000-8000-000000000020';
const _sourceId = '00000000-0000-4000-8000-000000000021';
const _jobId = '00000000-0000-4000-8000-000000000022';

class _ActorsGateway implements ActorsGateway {
  const _ActorsGateway();

  @override
  Future<ActorPageDto> listActors({
    required ActorListScope scope,
    String? cursor,
  }) async => const ActorPageDto(items: <ActorSummaryDto>[], nextCursor: null);

  @override
  Future<ActorDetailDto> getActor(String actorId) async => ActorDetailDto(
    id: actorId,
    displayName: '测试女优',
    nameJa: 'テスト',
    nameZh: '测试女优',
    aliases: const <String>[],
    profileUrl: null,
    favorite: false,
    bio: null,
    bioOriginal: null,
    galleryUrls: const <String>[],
    movies: const <MovieSummaryDto>[],
  );

  @override
  Future<void> setFavorite(String actorId, {required bool enabled}) async {}
}

class _MovieDetailGateway implements MovieDetailGateway {
  const _MovieDetailGateway();

  @override
  Future<MovieDetailDto> getMovie(String movieId) async => MovieDetailDto(
    id: movieId,
    number: 'ABC-123',
    title: '路由影片',
    titleOriginal: null,
    coverUrl: null,
    publishDate: null,
    labels: const <String>[],
    favorite: false,
    sourceCount: 1,
    progress: null,
    releaseDate: null,
    maker: null,
    series: null,
    director: null,
    score: null,
    description: null,
    descriptionOriginal: null,
    actors: const <ActorSummaryDto>[],
    tags: const <String>[],
    plotImageUrls: const <String>[],
    sources: const <MovieSourceDto>[
      MovieSourceDto(
        id: _sourceId,
        website: MovieSourceWebsite.sehuatang,
        externalPostId: 1,
        title: '路由来源',
        publishDate: null,
        category: '中文字幕',
        labels: <String>['subtitle'],
        resourceSizeMb: 1024,
        videoFileSizeBytes: null,
        availability: MovieSourceAvailability.available,
      ),
    ],
  );

  @override
  Future<List<int>> loadCatalogImage(String imageUrl) async => <int>[];

  @override
  Future<void> setFavorite(String movieId, {required bool enabled}) async {}
}

class _WaitingPlayGateway implements PlayRequestGateway {
  final List<String> movieIds = <String>[];
  final List<String> sourceIds = <String>[];

  @override
  Future<PlayRequestResultDto> request({
    required String movieId,
    required String sourceId,
    required String idempotencyKey,
  }) async {
    movieIds.add(movieId);
    sourceIds.add(sourceId);
    return PlayRequestResultDto(
      disposition: PlayDisposition.started,
      waitDeadline: DateTime.utc(2026, 7, 31, 12, 1),
      cacheJob: _routeJob('submitting'),
    );
  }

  @override
  Future<CacheJobDto> cancel(String jobId, {required bool confirmed}) async =>
      _routeJob('cleaned');
}

class _RouteClock implements PlayRequestClock {
  const _RouteClock();

  @override
  Duration monotonicNow() => Duration.zero;

  @override
  DateTime wallNow() => DateTime.utc(2026, 7, 31, 12);
}

CacheJobDto _routeJob(String status) => CacheJobDto(
  id: _jobId,
  movieId: _movieId,
  sourceId: _sourceId,
  status: status,
  remotePercent: 0,
  errorCode: null,
  mediaCandidates: const <RemoteMediaDto>[],
  selectedMediaIds: status == 'ready' ? const <String>[_mediaId] : const [],
  subtitles: const <SubtitleOptionDto>[],
  readyAt: null,
  expiresAt: null,
  createdAt: DateTime.utc(2026, 7, 31, 12),
  updatedAt: DateTime.utc(2026, 7, 31, 12),
);

class _RoutePlaybackGateway
    implements
        PlaybackGateway,
        SubtitleDownloadGateway,
        PlaybackProgressGateway {
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
      'https://server.test/api/v1/playback/streams/$_sessionId',
    ),
    expiresAt: DateTime.utc(2026, 8, 1),
    subtitleCacheExpiresAt: DateTime.utc(2026, 8, 1),
    mediaQueue: <PlaybackQueueItemDto>[
      PlaybackQueueItemDto(
        sessionId: _sessionId,
        media: const RemoteMediaDto(
          id: _mediaId,
          candidateId: _candidateId,
          name: 'route.mp4',
          sizeBytes: 100,
          durationSeconds: 60,
          sequenceNo: 0,
          isValid: true,
        ),
        streamUri: Uri.parse(
          'https://server.test/api/v1/playback/streams/$_sessionId',
        ),
      ),
    ],
    subtitles: const [],
    progress: null,
  );

  @override
  Future<List<int>> downloadSubtitle({
    required String playbackSessionId,
    required String subtitleId,
  }) async => const <int>[];

  @override
  Future<PlaybackProgressDto> updateProgress({
    required String movieId,
    required double positionSeconds,
    required double? durationSeconds,
    required int version,
  }) async => PlaybackProgressDto(
    positionSeconds: positionSeconds,
    durationSeconds: durationSeconds,
    completed: false,
    version: version + 1,
  );

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
      completed: false,
      version: version + 1,
    ),
  );
}

class _RoutePlaybackEngine implements PlaybackEngine {
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
    required String? language,
  }) async {}
  @override
  Future<void> toggleFullscreen() async {}
  @override
  Future<void> dispose() async {}
}

const _mediaId = '00000000-0000-4000-8000-000000000023';
const _candidateId = '00000000-0000-4000-8000-000000000024';
const _sessionId = '00000000-0000-4000-8000-000000000025';

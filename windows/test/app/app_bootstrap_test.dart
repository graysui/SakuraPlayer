import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:sakuraplayer_windows/app/app.dart';
import 'package:sakuraplayer_windows/app/fullscreen_player_page.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/features/actors/data/actors_api.dart';
import 'package:sakuraplayer_windows/features/actors/presentation/actor_detail_page.dart';
import 'package:sakuraplayer_windows/features/auth/domain/auth_session_state.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/auth_controller.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/login_page.dart';
import 'package:sakuraplayer_windows/features/library/data/movies_api.dart';
import 'package:sakuraplayer_windows/features/movies/data/movie_detail_api.dart';
import 'package:sakuraplayer_windows/features/movies/presentation/movie_detail_page.dart';
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
    expect(find.byType(FullscreenPlayerPage), findsNothing);
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
        ],
        child: const SakuraPlayerApp(),
      ),
    );
    await tester.pumpAndSettle();

    GoRouter.of(
      tester.element(find.byType(DesktopShell)),
    ).go(const FullscreenPlayerRoute().location);
    await tester.pumpAndSettle();

    expect(find.byType(FullscreenPlayerPage), findsOneWidget);
    final playerIcon = find.byIcon(Icons.play_circle_outline);
    expect(Theme.of(tester.element(playerIcon)).brightness, Brightness.dark);
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
      '/player',
    });
    expect(appRouteLocations.any((path) => path.contains('age')), isFalse);
    expect(appRouteLocations.any((path) => path.contains('external')), isFalse);
    expect(() => ActorDetailRoute('not-an-actor-id'), throwsArgumentError);
    expect(() => MovieDetailRoute('not-a-movie-id'), throwsArgumentError);
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
    sources: const <MovieSourceDto>[],
  );

  @override
  Future<List<int>> loadCatalogImage(String imageUrl) async => <int>[];

  @override
  Future<void> setFavorite(String movieId, {required bool enabled}) async {}
}

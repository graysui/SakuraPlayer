import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:sakuraplayer_windows/app/fullscreen_player_page.dart';
import 'package:sakuraplayer_windows/features/actors/data/actors_api.dart';
import 'package:sakuraplayer_windows/features/actors/presentation/actor_detail_page.dart';
import 'package:sakuraplayer_windows/features/actors/presentation/actors_page.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/auth_controller.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/login_page.dart';
import 'package:sakuraplayer_windows/features/cache/presentation/cache_page.dart';
import 'package:sakuraplayer_windows/features/library/presentation/library_page.dart';
import 'package:sakuraplayer_windows/features/movies/data/movie_detail_api.dart';
import 'package:sakuraplayer_windows/features/movies/presentation/movie_detail_page.dart';
import 'package:sakuraplayer_windows/features/rankings/presentation/rankings_page.dart';
import 'package:sakuraplayer_windows/features/settings/presentation/diagnostics_page.dart';
import 'package:sakuraplayer_windows/features/settings/presentation/settings_page.dart';
import 'package:sakuraplayer_windows/widgets/shell/desktop_shell.dart';

sealed class AppRouteLocation {
  const AppRouteLocation();

  String get location;

  void go(BuildContext context) => context.go(location);
}

final class LoginRoute extends AppRouteLocation {
  const LoginRoute();

  @override
  String get location => '/login';
}

final class LibraryRoute extends AppRouteLocation {
  const LibraryRoute();

  @override
  String get location => '/app/library';
}

final class RankingsRoute extends AppRouteLocation {
  const RankingsRoute();

  @override
  String get location => '/app/rankings';
}

final class ActorsRoute extends AppRouteLocation {
  const ActorsRoute();

  @override
  String get location => '/app/actors';
}

final class ActorDetailRoute extends AppRouteLocation {
  ActorDetailRoute(this.actorId) {
    requireActorId(actorId);
  }

  final String actorId;

  @override
  String get location => '/app/actors/${Uri.encodeComponent(actorId)}';
}

final class MovieDetailRoute extends AppRouteLocation {
  MovieDetailRoute(this.movieId) {
    requireMovieId(movieId);
  }

  final String movieId;

  @override
  String get location => '/app/movies/${Uri.encodeComponent(movieId)}';
}

final class CacheStatusRoute extends AppRouteLocation {
  const CacheStatusRoute();

  @override
  String get location => '/app/cache';
}

final class SettingsRoute extends AppRouteLocation {
  const SettingsRoute();

  @override
  String get location => '/app/settings';
}

final class SettingsDiagnosticsRoute extends AppRouteLocation {
  const SettingsDiagnosticsRoute();

  @override
  String get location => '/app/settings/diagnostics';
}

final class FullscreenPlayerRoute extends AppRouteLocation {
  const FullscreenPlayerRoute();

  @override
  String get location => '/player';
}

const appRouteLocations = <String>{
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
};

final appRouterProvider = Provider<GoRouter>((ref) {
  final authSession = ref.watch(authSessionStateProvider);
  final router = GoRouter(
    initialLocation: const LibraryRoute().location,
    redirect: (context, state) {
      final isLogin = state.matchedLocation == const LoginRoute().location;
      if (!authSession.isAuthenticated && !isLogin) {
        return const LoginRoute().location;
      }
      if (authSession.isAuthenticated && isLogin) {
        return const LibraryRoute().location;
      }
      return null;
    },
    routes: [
      GoRoute(
        path: const LoginRoute().location,
        builder: (context, state) => const LoginPage(),
      ),
      ShellRoute(
        builder: (context, state, child) {
          final destination = switch (state.fullPath) {
            '/app/library' => ShellDestination.library,
            '/app/rankings' => ShellDestination.rankings,
            '/app/actors' => ShellDestination.actors,
            '/app/actors/:actor_id' => ShellDestination.actors,
            '/app/movies/:movie_id' => ShellDestination.library,
            _ => null,
          };
          return DesktopShell(
            selectedDestination: destination,
            onDestinationSelected: (selected) {
              switch (selected) {
                case ShellDestination.library:
                  const LibraryRoute().go(context);
                case ShellDestination.rankings:
                  const RankingsRoute().go(context);
                case ShellDestination.actors:
                  const ActorsRoute().go(context);
              }
            },
            onActorSelected: (actorId) => ActorDetailRoute(actorId).go(context),
            onMovieSelected: (movieId) => MovieDetailRoute(movieId).go(context),
            onCachePressed: () => const CacheStatusRoute().go(context),
            onSettingsPressed: () => const SettingsRoute().go(context),
            child: child,
          );
        },
        routes: [
          GoRoute(
            path: const LibraryRoute().location,
            builder:
                (context, state) => LibraryPage(
                  key: const ValueKey('library-page'),
                  onOpenMovie:
                      (movieId) => MovieDetailRoute(movieId).go(context),
                ),
          ),
          GoRoute(
            path: const RankingsRoute().location,
            builder:
                (context, state) => RankingsPage(
                  key: ValueKey('rankings-page'),
                  onOpenSettings: () => const SettingsRoute().go(context),
                  onOpenMovie:
                      (movieId) => MovieDetailRoute(movieId).go(context),
                ),
          ),
          GoRoute(
            path: const ActorsRoute().location,
            builder:
                (context, state) => ActorsPage(
                  key: const ValueKey('actors-page'),
                  onOpenActor:
                      (actorId) => ActorDetailRoute(actorId).go(context),
                ),
            routes: [
              GoRoute(
                path: ':actor_id',
                redirect:
                    (context, state) =>
                        isValidActorId(state.pathParameters['actor_id'] ?? '')
                            ? null
                            : const ActorsRoute().location,
                builder:
                    (context, state) => ActorDetailPage(
                      key: ValueKey(
                        'actor-detail-${state.pathParameters['actor_id']}',
                      ),
                      actorId: state.pathParameters['actor_id']!,
                      onBack: () => const ActorsRoute().go(context),
                      onOpenMovie:
                          (movieId) => MovieDetailRoute(movieId).go(context),
                    ),
              ),
            ],
          ),
          GoRoute(
            path: '/app/movies/:movie_id',
            redirect:
                (context, state) =>
                    isValidMovieId(state.pathParameters['movie_id'] ?? '')
                        ? null
                        : const LibraryRoute().location,
            builder:
                (context, state) => MovieDetailPage(
                  key: ValueKey(
                    'movie-detail-${state.pathParameters['movie_id']}',
                  ),
                  movieId: state.pathParameters['movie_id']!,
                  onBack: () {
                    if (context.canPop()) {
                      context.pop();
                    } else {
                      const LibraryRoute().go(context);
                    }
                  },
                  onOpenActor:
                      (actorId) => ActorDetailRoute(actorId).go(context),
                ),
          ),
          GoRoute(
            path: const CacheStatusRoute().location,
            builder:
                (context, state) =>
                    const CachePage(key: ValueKey('cache-page')),
          ),
          GoRoute(
            path: const SettingsRoute().location,
            builder:
                (context, state) => SettingsPage(
                  key: const ValueKey('settings-page'),
                  onOpenDiagnostics:
                      () => const SettingsDiagnosticsRoute().go(context),
                ),
            routes: [
              GoRoute(
                path: 'diagnostics',
                builder:
                    (context, state) => DiagnosticsPage(
                      key: const ValueKey('diagnostics-page'),
                      onBack: () {
                        if (context.canPop()) {
                          context.pop();
                        } else {
                          const SettingsRoute().go(context);
                        }
                      },
                    ),
              ),
            ],
          ),
        ],
      ),
      GoRoute(
        path: const FullscreenPlayerRoute().location,
        builder: (context, state) => const FullscreenPlayerPage(),
      ),
    ],
  );
  ref.onDispose(router.dispose);
  return router;
});

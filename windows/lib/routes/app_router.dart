import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:sakuraplayer_windows/app/fullscreen_player_page.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/auth_controller.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/login_page.dart';
import 'package:sakuraplayer_windows/features/library/presentation/library_page.dart';
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
  '/app/cache',
  '/app/settings',
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
          final destination = switch (state.matchedLocation) {
            '/app/library' => ShellDestination.library,
            '/app/rankings' => ShellDestination.rankings,
            '/app/actors' => ShellDestination.actors,
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
            onCachePressed: () => const CacheStatusRoute().go(context),
            onSettingsPressed: () => const SettingsRoute().go(context),
            child: child,
          );
        },
        routes: [
          GoRoute(
            path: const LibraryRoute().location,
            builder:
                (context, state) =>
                    const LibraryPage(key: ValueKey('library-page')),
          ),
          GoRoute(
            path: const RankingsRoute().location,
            builder:
                (context, state) => const _ShellPage(
                  key: ValueKey('rankings-page'),
                  title: '排行榜',
                ),
          ),
          GoRoute(
            path: const ActorsRoute().location,
            builder:
                (context, state) =>
                    const _ShellPage(key: ValueKey('actors-page'), title: '女优'),
          ),
          GoRoute(
            path: const CacheStatusRoute().location,
            builder:
                (context, state) => const _ShellPage(
                  key: ValueKey('cache-page'),
                  title: '缓存状态',
                ),
          ),
          GoRoute(
            path: const SettingsRoute().location,
            builder:
                (context, state) => const _ShellPage(
                  key: ValueKey('settings-page'),
                  title: '管理员设置',
                ),
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

class _ShellPage extends StatelessWidget {
  const _ShellPage({required this.title, super.key});

  final String title;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Text(title, style: Theme.of(context).textTheme.headlineSmall),
    );
  }
}

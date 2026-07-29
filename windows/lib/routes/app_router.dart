import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:sakuraplayer_windows/app/fullscreen_player_page.dart';
import 'package:sakuraplayer_windows/app/shell_placeholder_page.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/auth_controller.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/login_page.dart';

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

final class ShellRoute extends AppRouteLocation {
  const ShellRoute();

  @override
  String get location => '/app';
}

final class FullscreenPlayerRoute extends AppRouteLocation {
  const FullscreenPlayerRoute();

  @override
  String get location => '/player';
}

const appRouteLocations = <String>{'/login', '/app', '/player'};

final appRouterProvider = Provider<GoRouter>((ref) {
  final authSession = ref.watch(authSessionStateProvider);
  final router = GoRouter(
    initialLocation: const ShellRoute().location,
    redirect: (context, state) {
      final isLogin = state.matchedLocation == const LoginRoute().location;
      if (!authSession.isAuthenticated && !isLogin) {
        return const LoginRoute().location;
      }
      if (authSession.isAuthenticated && isLogin) {
        return const ShellRoute().location;
      }
      return null;
    },
    routes: [
      GoRoute(
        path: const LoginRoute().location,
        builder: (context, state) => const LoginPage(),
      ),
      GoRoute(
        path: const ShellRoute().location,
        builder: (context, state) => const ShellPlaceholderPage(),
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

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:sakuraplayer_windows/app/app.dart';
import 'package:sakuraplayer_windows/app/fullscreen_player_page.dart';
import 'package:sakuraplayer_windows/features/auth/domain/auth_session_state.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/auth_controller.dart';
import 'package:sakuraplayer_windows/features/auth/presentation/login_page.dart';
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
      '/app/cache',
      '/app/settings',
      '/player',
    });
    expect(appRouteLocations.any((path) => path.contains('age')), isFalse);
    expect(appRouteLocations.any((path) => path.contains('external')), isFalse);
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

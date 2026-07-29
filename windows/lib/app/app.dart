import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/routes/app_router.dart';
import 'package:sakuraplayer_windows/theme/app_theme.dart';

class SakuraPlayerApp extends ConsumerWidget {
  const SakuraPlayerApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(appRouterProvider);
    final themeMode = ref.watch(appThemeModeProvider);

    return MaterialApp.router(
      title: 'SakuraPlayer',
      debugShowCheckedModeBanner: false,
      theme: SakuraAppTheme.light,
      darkTheme: SakuraAppTheme.dark,
      themeMode: themeMode.materialThemeMode,
      routerConfig: router,
    );
  }
}

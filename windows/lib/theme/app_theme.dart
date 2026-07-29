import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

enum AppThemeMode { system, light, dark }

extension AppThemeModeMaterial on AppThemeMode {
  ThemeMode get materialThemeMode => switch (this) {
    AppThemeMode.system => ThemeMode.system,
    AppThemeMode.light => ThemeMode.light,
    AppThemeMode.dark => ThemeMode.dark,
  };
}

class AppThemeModeController extends Notifier<AppThemeMode> {
  @override
  AppThemeMode build() => AppThemeMode.system;

  void setMode(AppThemeMode mode) => state = mode;
}

final appThemeModeProvider =
    NotifierProvider<AppThemeModeController, AppThemeMode>(
      AppThemeModeController.new,
    );

abstract final class SakuraAppTheme {
  static final ThemeData light = _createTheme(
    brightness: Brightness.light,
    background: const Color(0xFFF7F8FA),
    surface: Colors.white,
    foreground: const Color(0xFF202124),
    primary: const Color(0xFFB4233A),
  );

  static final ThemeData dark = _createTheme(
    brightness: Brightness.dark,
    background: const Color(0xFF17191C),
    surface: const Color(0xFF22252A),
    foreground: const Color(0xFFF1F3F4),
    primary: const Color(0xFFFF6B81),
  );

  static ThemeData _createTheme({
    required Brightness brightness,
    required Color background,
    required Color surface,
    required Color foreground,
    required Color primary,
  }) {
    final scheme = ColorScheme.fromSeed(
      seedColor: primary,
      brightness: brightness,
      surface: surface,
    );
    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: scheme,
      scaffoldBackgroundColor: background,
      textTheme: ThemeData(
        brightness: brightness,
      ).textTheme.apply(bodyColor: foreground, displayColor: foreground),
      inputDecorationTheme: const InputDecorationTheme(
        border: OutlineInputBorder(),
      ),
      cardTheme: const CardThemeData(
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.all(Radius.circular(8)),
        ),
      ),
    );
  }
}

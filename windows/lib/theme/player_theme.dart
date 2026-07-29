import 'package:flutter/material.dart';

abstract final class SakuraPlayerTheme {
  static const background = Color(0xFF090A0C);
  static const surface = Color(0xFF17191D);
  static const foreground = Color(0xFFF5F7FA);
  static const accent = Color(0xFFFF6B81);

  static final ThemeData dark = ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    scaffoldBackgroundColor: background,
    colorScheme: const ColorScheme.dark(
      primary: accent,
      surface: surface,
      onSurface: foreground,
    ),
  );
}

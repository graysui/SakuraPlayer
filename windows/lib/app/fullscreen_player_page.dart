import 'package:flutter/material.dart';
import 'package:sakuraplayer_windows/theme/player_theme.dart';

class FullscreenPlayerPage extends StatelessWidget {
  const FullscreenPlayerPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Theme(
      data: SakuraPlayerTheme.dark,
      child: const Scaffold(
        backgroundColor: SakuraPlayerTheme.background,
        body: SafeArea(
          child: Stack(
            children: [
              Center(
                child: Icon(
                  Icons.play_circle_outline,
                  size: 64,
                  color: SakuraPlayerTheme.foreground,
                ),
              ),
              Positioned(left: 12, top: 12, child: BackButton()),
            ],
          ),
        ),
      ),
    );
  }
}

import 'package:flutter/material.dart';
import 'package:sakuraplayer_windows/routes/app_router.dart';

class ShellPlaceholderPage extends StatelessWidget {
  const ShellPlaceholderPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('SakuraPlayer'),
        actions: [
          IconButton(
            onPressed: () => const FullscreenPlayerRoute().go(context),
            tooltip: '打开播放器',
            icon: const Icon(Icons.play_circle_outline),
          ),
        ],
      ),
      body: const Center(child: Text('媒体库')),
    );
  }
}

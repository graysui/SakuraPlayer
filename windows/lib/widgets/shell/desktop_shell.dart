import 'package:flutter/material.dart';
import 'package:sakuraplayer_windows/features/cache/presentation/cache_badge.dart';
import 'package:sakuraplayer_windows/features/search/presentation/search_overlay.dart';

enum ShellDestination { library, rankings, actors }

class DesktopShell extends StatelessWidget {
  const DesktopShell({
    required this.selectedDestination,
    required this.onDestinationSelected,
    required this.onActorSelected,
    this.onMovieSelected,
    required this.onCachePressed,
    required this.onSettingsPressed,
    required this.child,
    super.key,
  });

  final ShellDestination? selectedDestination;
  final ValueChanged<ShellDestination> onDestinationSelected;
  final ValueChanged<String> onActorSelected;
  final ValueChanged<String>? onMovieSelected;
  final VoidCallback onCachePressed;
  final VoidCallback onSettingsPressed;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final extended = constraints.maxWidth >= 760;
            return Row(
              children: [
                NavigationRail(
                  extended: extended,
                  minWidth: 72,
                  minExtendedWidth: 208,
                  selectedIndex: selectedDestination?.index,
                  groupAlignment: -0.8,
                  onDestinationSelected:
                      (index) =>
                          onDestinationSelected(ShellDestination.values[index]),
                  leading: Padding(
                    padding: const EdgeInsets.only(top: 8, bottom: 20),
                    child:
                        extended
                            ? const SizedBox(
                              width: 176,
                              child: Row(
                                children: [
                                  Icon(Icons.local_movies_outlined),
                                  SizedBox(width: 12),
                                  Expanded(
                                    child: Text(
                                      'SakuraPlayer',
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                  ),
                                ],
                              ),
                            )
                            : const Icon(Icons.local_movies_outlined),
                  ),
                  destinations: const [
                    NavigationRailDestination(
                      icon: Icon(Icons.video_library_outlined),
                      selectedIcon: Icon(Icons.video_library),
                      label: Text('媒体库'),
                    ),
                    NavigationRailDestination(
                      icon: Icon(Icons.leaderboard_outlined),
                      selectedIcon: Icon(Icons.leaderboard),
                      label: Text('排行榜'),
                    ),
                    NavigationRailDestination(
                      icon: Icon(Icons.people_outline),
                      selectedIcon: Icon(Icons.people),
                      label: Text('女优'),
                    ),
                  ],
                ),
                const VerticalDivider(width: 1),
                Expanded(
                  child: Column(
                    children: [
                      SizedBox(
                        height: 68,
                        child: Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 16),
                          child: Row(
                            children: [
                              Expanded(
                                child: Align(
                                  alignment: Alignment.centerLeft,
                                  child: ConstrainedBox(
                                    constraints: BoxConstraints(
                                      maxWidth: extended ? 420 : 64,
                                    ),
                                    child: SearchOverlay(
                                      compact: !extended,
                                      onMovieSelected: onMovieSelected,
                                      onActorSelected: onActorSelected,
                                    ),
                                  ),
                                ),
                              ),
                              const SizedBox(width: 12),
                              CacheBadge(onPressed: onCachePressed),
                              const SizedBox(width: 8),
                              IconButton(
                                onPressed: onSettingsPressed,
                                tooltip: '管理员设置',
                                icon: const Icon(Icons.settings_outlined),
                              ),
                            ],
                          ),
                        ),
                      ),
                      const Divider(height: 1),
                      Expanded(child: child),
                    ],
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:sakuraplayer_windows/features/library/data/movies_api.dart';
import 'package:sakuraplayer_windows/features/playback/presentation/progress_controller.dart';

typedef MovieCoverLoader = Future<List<int>> Function(String coverUrl);

class MovieCard extends StatefulWidget {
  const MovieCard({
    required this.movie,
    required this.coverLoader,
    this.onOpen,
    this.onPlay,
    this.liveProgress,
    super.key,
  });

  final MovieSummaryDto movie;
  final MovieCoverLoader coverLoader;
  final VoidCallback? onOpen;
  final VoidCallback? onPlay;
  final LivePlaybackProgress? liveProgress;

  @override
  State<MovieCard> createState() => _MovieCardState();
}

class _MovieCardState extends State<MovieCard> {
  Future<List<int>>? _cover;

  @override
  void initState() {
    super.initState();
    _loadCover();
  }

  @override
  void didUpdateWidget(MovieCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.movie.coverUrl != widget.movie.coverUrl ||
        oldWidget.coverLoader != widget.coverLoader) {
      _loadCover();
    }
  }

  void _loadCover() {
    final coverUrl = widget.movie.coverUrl;
    _cover = coverUrl == null ? null : widget.coverLoader(coverUrl);
  }

  @override
  Widget build(BuildContext context) {
    final movie = widget.movie;
    final progress = movie.progress;
    final liveProgress = freshestLivePlaybackProgress(
      widget.liveProgress,
      progress?.version,
    );
    final progressFraction = liveProgress?.fraction ?? progress?.fraction;
    final completed = liveProgress?.completed ?? progress?.completed ?? false;
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: widget.onOpen,
      child: Card(
        margin: EdgeInsets.zero,
        clipBehavior: Clip.antiAlias,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SizedBox(
              height: 264,
              child: Stack(
                fit: StackFit.expand,
                children: [
                  ColoredBox(
                    color:
                        Theme.of(context).colorScheme.surfaceContainerHighest,
                    child: Center(
                      child: AspectRatio(
                        key: const ValueKey('movie-poster-aspect'),
                        aspectRatio: 2 / 3,
                        child: _Cover(
                          future: _cover,
                          hasCover: movie.coverUrl != null,
                        ),
                      ),
                    ),
                  ),
                  if (movie.labels.isNotEmpty)
                    Positioned(
                      left: 8,
                      bottom: 8,
                      child: Wrap(
                        spacing: 4,
                        children: [
                          for (final label in movie.labels.take(2))
                            _PosterBadge(label: _labelNames[label] ?? label),
                        ],
                      ),
                    ),
                  if (movie.favorite)
                    const Positioned(
                      right: 8,
                      top: 8,
                      child: _PosterBadge(icon: Icons.favorite),
                    ),
                ],
              ),
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(10, 8, 10, 8),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    SizedBox(
                      height: 40,
                      child: Text(
                        movie.title,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.titleSmall,
                      ),
                    ),
                    SizedBox(
                      height: 20,
                      child: Row(
                        children: [
                          Expanded(
                            child: Text(
                              movie.number,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: Theme.of(context).textTheme.labelMedium,
                            ),
                          ),
                          Text(
                            '${movie.sourceCount} 个来源',
                            style: Theme.of(context).textTheme.labelSmall,
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 4),
                    SizedBox(
                      height: 4,
                      child:
                          progressFraction == null
                              ? const SizedBox.shrink()
                              : LinearProgressIndicator(
                                value: progressFraction,
                                borderRadius: BorderRadius.circular(2),
                              ),
                    ),
                    const SizedBox(height: 6),
                    SizedBox(
                      height: 36,
                      child: FilledButton.tonalIcon(
                        onPressed: widget.onPlay ?? widget.onOpen,
                        icon: Icon(
                          completed
                              ? Icons.check_circle_outline
                              : Icons.play_arrow,
                          size: 18,
                        ),
                        label: FittedBox(
                          fit: BoxFit.scaleDown,
                          child: Text(
                            liveProgress == null
                                ? movieProgressLabel(progress)
                                : liveMovieProgressLabel(liveProgress),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Cover extends StatelessWidget {
  const _Cover({required this.future, required this.hasCover});

  final Future<List<int>>? future;
  final bool hasCover;

  @override
  Widget build(BuildContext context) {
    if (!hasCover || future == null) {
      return const _CoverPlaceholder(icon: Icons.movie_outlined);
    }
    return FutureBuilder<List<int>>(
      future: future,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(
            child: SizedBox.square(
              dimension: 28,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
          );
        }
        if (snapshot.hasError || snapshot.data == null) {
          return const _CoverPlaceholder(icon: Icons.broken_image_outlined);
        }
        return Image.memory(
          Uint8List.fromList(snapshot.data!),
          fit: BoxFit.cover,
          errorBuilder:
              (context, error, stackTrace) =>
                  const _CoverPlaceholder(icon: Icons.broken_image_outlined),
        );
      },
    );
  }
}

class _CoverPlaceholder extends StatelessWidget {
  const _CoverPlaceholder({required this.icon});

  final IconData icon;

  @override
  Widget build(BuildContext context) => ColoredBox(
    color: Theme.of(context).colorScheme.surfaceContainerHigh,
    child: Center(
      child: Icon(
        icon,
        size: 42,
        color: Theme.of(context).colorScheme.onSurfaceVariant,
      ),
    ),
  );
}

class _PosterBadge extends StatelessWidget {
  const _PosterBadge({this.label, this.icon});

  final String? label;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: colors.surface.withValues(alpha: 0.92),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
        child:
            icon == null
                ? Text(label!, style: Theme.of(context).textTheme.labelSmall)
                : Icon(icon, size: 14, color: colors.primary),
      ),
    );
  }
}

String movieProgressLabel(PlaybackProgressDto? progress) {
  if (progress == null) return '播放';
  if (progress.completed) return '已看完';
  final fraction = progress.fraction;
  if (fraction != null) return '继续播放 ${(fraction * 100).round()}%';
  return '已播放 ${_formatDuration(progress.positionSeconds)}';
}

String liveMovieProgressLabel(LivePlaybackProgress progress) {
  if (progress.completed) return '已看完';
  final fraction = progress.fraction;
  if (fraction != null) return '继续播放 ${(fraction * 100).round()}%';
  return '已播放 ${_formatDuration(progress.positionSeconds)}';
}

String _formatDuration(num seconds) {
  final total = seconds.floor().clamp(0, 359999);
  final hours = total ~/ 3600;
  final minutes = (total % 3600) ~/ 60;
  final remaining = total % 60;
  final minuteText = minutes.toString().padLeft(2, '0');
  final secondText = remaining.toString().padLeft(2, '0');
  return hours > 0
      ? '${hours.toString().padLeft(2, '0')}:$minuteText:$secondText'
      : '$minuteText:$secondText';
}

const _labelNames = <String, String>{
  'subtitle': '字幕',
  'cracked': '破解',
  '4k': '4K',
  'censored': '有码',
};

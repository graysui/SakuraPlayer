import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/features/actors/data/actors_api.dart';
import 'package:sakuraplayer_windows/features/actors/presentation/actors_controller.dart';
import 'package:sakuraplayer_windows/features/actors/presentation/gfriends_image.dart';
import 'package:sakuraplayer_windows/features/library/data/movies_api.dart';
import 'package:sakuraplayer_windows/features/library/presentation/movie_card.dart';

class ActorDetailPage extends ConsumerStatefulWidget {
  const ActorDetailPage({
    required this.actorId,
    this.onBack,
    this.onOpenMovie,
    super.key,
  });

  final String actorId;
  final VoidCallback? onBack;
  final ValueChanged<String>? onOpenMovie;

  @override
  ConsumerState<ActorDetailPage> createState() => _ActorDetailPageState();
}

class _ActorDetailPageState extends ConsumerState<ActorDetailPage> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        unawaited(
          ref.read(actorDetailControllerProvider.notifier).load(widget.actorId),
        );
      }
    });
  }

  @override
  void didUpdateWidget(ActorDetailPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.actorId != widget.actorId) {
      unawaited(
        ref.read(actorDetailControllerProvider.notifier).load(widget.actorId),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(actorDetailControllerProvider);
    if (state.status == ActorDetailStatus.idle ||
        state.status == ActorDetailStatus.loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (state.status == ActorDetailStatus.failed || state.detail == null) {
      return _DetailMessage(
        icon: Icons.cloud_off_outlined,
        title: state.errorCode == 'resource_not_found' ? '女优资料不存在' : '女优资料加载失败',
        onRetry:
            () => unawaited(
              ref.read(actorDetailControllerProvider.notifier).retry(),
            ),
      );
    }
    return _detail(context, state, state.detail!);
  }

  Widget _detail(
    BuildContext context,
    ActorDetailState state,
    ActorDetailDto detail,
  ) => LayoutBuilder(
    builder: (context, constraints) {
      final horizontalPadding = constraints.maxWidth < 900 ? 16.0 : 24.0;
      final galleryWidth = constraints.maxWidth - horizontalPadding * 2;
      final galleryColumns = ((galleryWidth + 12) / (180 + 12)).floor().clamp(
        2,
        8,
      );
      final movieColumns = ((galleryWidth + 16) / (184 + 16)).floor().clamp(
        1,
        100,
      );
      final coverLoader = ref.read(moviesGatewayProvider).loadCover;
      return CustomScrollView(
        slivers: [
          SliverPadding(
            padding: EdgeInsets.fromLTRB(
              horizontalPadding,
              16,
              horizontalPadding,
              24,
            ),
            sliver: SliverToBoxAdapter(
              child: _profileHeader(context, state, detail),
            ),
          ),
          SliverPadding(
            padding: EdgeInsets.fromLTRB(
              horizontalPadding,
              0,
              horizontalPadding,
              12,
            ),
            sliver: SliverToBoxAdapter(
              child: Text('写真', style: Theme.of(context).textTheme.titleLarge),
            ),
          ),
          if (detail.galleryUrls.isEmpty)
            SliverPadding(
              padding: EdgeInsets.fromLTRB(
                horizontalPadding,
                8,
                horizontalPadding,
                28,
              ),
              sliver: const SliverToBoxAdapter(
                child: _EmptySection(
                  icon: Icons.photo_library_outlined,
                  label: '暂无写真',
                ),
              ),
            )
          else
            SliverPadding(
              padding: EdgeInsets.fromLTRB(
                horizontalPadding,
                0,
                horizontalPadding,
                28,
              ),
              sliver: SliverGrid(
                delegate: SliverChildBuilderDelegate(
                  (context, index) => Material(
                    key: ValueKey('gallery-thumbnail-$index'),
                    clipBehavior: Clip.antiAlias,
                    borderRadius: BorderRadius.circular(6),
                    color: Theme.of(context).colorScheme.surfaceContainerHigh,
                    child: InkWell(
                      onTap:
                          () => showDialog<void>(
                            context: context,
                            builder:
                                (context) => _GalleryViewer(
                                  urls: detail.galleryUrls,
                                  initialIndex: index,
                                ),
                          ),
                      child: GfriendsImage(
                        url: detail.galleryUrls[index],
                        fit: BoxFit.cover,
                        missingLabel: '暂无写真',
                        missingIcon: Icons.photo_outlined,
                      ),
                    ),
                  ),
                  childCount: detail.galleryUrls.length,
                ),
                gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: galleryColumns,
                  mainAxisExtent: 220,
                  crossAxisSpacing: 12,
                  mainAxisSpacing: 12,
                ),
              ),
            ),
          SliverPadding(
            padding: EdgeInsets.fromLTRB(
              horizontalPadding,
              0,
              horizontalPadding,
              12,
            ),
            sliver: SliverToBoxAdapter(
              child: Text(
                '关联影片',
                style: Theme.of(context).textTheme.titleLarge,
              ),
            ),
          ),
          if (detail.movies.isEmpty)
            SliverPadding(
              padding: EdgeInsets.fromLTRB(
                horizontalPadding,
                8,
                horizontalPadding,
                28,
              ),
              sliver: const SliverToBoxAdapter(
                child: _EmptySection(
                  icon: Icons.movie_outlined,
                  label: '暂无关联影片',
                ),
              ),
            )
          else
            SliverPadding(
              padding: EdgeInsets.fromLTRB(
                horizontalPadding,
                0,
                horizontalPadding,
                28,
              ),
              sliver: SliverGrid(
                delegate: SliverChildBuilderDelegate(
                  (context, index) => MovieCard(
                    movie: detail.movies[index],
                    coverLoader: coverLoader,
                    onOpen:
                        widget.onOpenMovie == null
                            ? null
                            : () =>
                                widget.onOpenMovie!(detail.movies[index].id),
                  ),
                  childCount: detail.movies.length,
                ),
                gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: movieColumns,
                  mainAxisExtent: 408,
                  crossAxisSpacing: 16,
                  mainAxisSpacing: 16,
                ),
              ),
            ),
        ],
      );
    },
  );

  Widget _profileHeader(
    BuildContext context,
    ActorDetailState state,
    ActorDetailDto detail,
  ) {
    final profile = SizedBox(
      width: 220,
      height: 300,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(6),
        child: GfriendsImage(
          url: detail.profileUrl,
          fit: BoxFit.cover,
          missingLabel: '暂无头像',
        ),
      ),
    );
    final information = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (widget.onBack != null) ...[
              IconButton(
                onPressed: widget.onBack,
                tooltip: '返回女优列表',
                icon: const Icon(Icons.arrow_back),
              ),
              const SizedBox(width: 4),
            ],
            Expanded(
              child: Text(
                detail.displayName,
                style: Theme.of(context).textTheme.headlineSmall,
              ),
            ),
            SizedBox.square(
              dimension: 48,
              child: IconButton(
                onPressed:
                    state.isFavoriteInFlight
                        ? null
                        : () => unawaited(
                          ref
                              .read(actorDetailControllerProvider.notifier)
                              .setFavorite(enabled: !detail.favorite),
                        ),
                tooltip: detail.favorite ? '取消收藏' : '收藏女优',
                icon:
                    state.isFavoriteInFlight
                        ? const SizedBox.square(
                          dimension: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                        : Icon(
                          detail.favorite
                              ? Icons.favorite
                              : Icons.favorite_outline,
                        ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 10),
        for (final name in _secondaryNames(detail))
          Padding(
            padding: const EdgeInsets.only(bottom: 4),
            child: Text(name, style: Theme.of(context).textTheme.titleMedium),
          ),
        const SizedBox(height: 10),
        Text(
          detail.aliases.isEmpty ? '暂无别名' : detail.aliases.join(' · '),
          style: Theme.of(context).textTheme.bodyMedium,
        ),
        const SizedBox(height: 18),
        Text('简介', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 6),
        Text(_biography(detail), style: Theme.of(context).textTheme.bodyMedium),
        if (state.favoriteErrorCode != null) ...[
          const SizedBox(height: 12),
          Text(
            '收藏更新失败，请重试',
            style: TextStyle(color: Theme.of(context).colorScheme.error),
          ),
        ],
      ],
    );
    return LayoutBuilder(
      builder:
          (context, constraints) =>
              constraints.maxWidth >= 760
                  ? Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      profile,
                      const SizedBox(width: 24),
                      Expanded(child: information),
                    ],
                  )
                  : Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Center(child: profile),
                      const SizedBox(height: 20),
                      information,
                    ],
                  ),
    );
  }
}

class _GalleryViewer extends StatefulWidget {
  const _GalleryViewer({required this.urls, required this.initialIndex});

  final List<String> urls;
  final int initialIndex;

  @override
  State<_GalleryViewer> createState() => _GalleryViewerState();
}

class _GalleryViewerState extends State<_GalleryViewer> {
  late int _index = widget.initialIndex;

  @override
  Widget build(BuildContext context) => Dialog(
    insetPadding: const EdgeInsets.all(24),
    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
    child: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 1000, maxHeight: 760),
      child: SizedBox(
        width: 1000,
        height: 700,
        child: Column(
          children: [
            SizedBox(
              height: 56,
              child: Row(
                children: [
                  const SizedBox(width: 16),
                  Text('${_index + 1} / ${widget.urls.length}'),
                  const Spacer(),
                  IconButton(
                    onPressed: () => Navigator.of(context).pop(),
                    tooltip: '关闭写真',
                    icon: const Icon(Icons.close),
                  ),
                  const SizedBox(width: 8),
                ],
              ),
            ),
            const Divider(height: 1),
            Expanded(
              child: Stack(
                children: [
                  Positioned.fill(
                    child: InteractiveViewer(
                      minScale: 0.5,
                      maxScale: 4,
                      child: Center(
                        child: GfriendsImage(
                          key: ValueKey('gallery-viewer-$_index'),
                          url: widget.urls[_index],
                          fit: BoxFit.contain,
                          missingLabel: '暂无写真',
                          missingIcon: Icons.photo_outlined,
                        ),
                      ),
                    ),
                  ),
                  Positioned(
                    left: 12,
                    top: 0,
                    bottom: 0,
                    child: Center(
                      child: IconButton.filledTonal(
                        onPressed:
                            _index == 0 ? null : () => setState(() => _index--),
                        tooltip: '上一张',
                        icon: const Icon(Icons.chevron_left),
                      ),
                    ),
                  ),
                  Positioned(
                    right: 12,
                    top: 0,
                    bottom: 0,
                    child: Center(
                      child: IconButton.filledTonal(
                        onPressed:
                            _index == widget.urls.length - 1
                                ? null
                                : () => setState(() => _index++),
                        tooltip: '下一张',
                        icon: const Icon(Icons.chevron_right),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    ),
  );
}

List<String> _secondaryNames(ActorDetailDto detail) {
  final result = <String>[];
  for (final value in <String?>[detail.nameZh, detail.nameJa]) {
    if (value != null && value.isNotEmpty && value != detail.displayName) {
      result.add(value);
    }
  }
  return result.toSet().toList(growable: false);
}

String _biography(ActorDetailDto detail) {
  for (final value in <String?>[detail.bio, detail.bioOriginal]) {
    final normalized = value?.trim();
    if (normalized != null && normalized.isNotEmpty) return normalized;
  }
  return '暂无简介';
}

class _EmptySection extends StatelessWidget {
  const _EmptySection({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) => SizedBox(
    height: 120,
    child: Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 38),
          const SizedBox(height: 8),
          Text(label),
        ],
      ),
    ),
  );
}

class _DetailMessage extends StatelessWidget {
  const _DetailMessage({
    required this.icon,
    required this.title,
    required this.onRetry,
  });

  final IconData icon;
  final String title;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => Center(
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 48),
        const SizedBox(height: 12),
        Text(title, style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 12),
        FilledButton.icon(
          onPressed: onRetry,
          icon: const Icon(Icons.refresh),
          label: const Text('重新加载'),
        ),
      ],
    ),
  );
}

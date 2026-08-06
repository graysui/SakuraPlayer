import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/features/library/presentation/movie_card.dart';
import 'package:sakuraplayer_windows/features/movies/data/movie_detail_api.dart';
import 'package:sakuraplayer_windows/features/movies/presentation/movie_detail_controller.dart';
import 'package:sakuraplayer_windows/features/movies/presentation/source_list.dart';
import 'package:sakuraplayer_windows/features/playback/presentation/progress_controller.dart';

class MovieDetailPage extends ConsumerStatefulWidget {
  const MovieDetailPage({
    required this.movieId,
    this.onBack,
    this.onOpenActor,
    this.onPlaySource,
    super.key,
  });

  final String movieId;
  final VoidCallback? onBack;
  final ValueChanged<String>? onOpenActor;
  final ValueChanged<String>? onPlaySource;

  @override
  ConsumerState<MovieDetailPage> createState() => _MovieDetailPageState();
}

class _MovieDetailPageState extends ConsumerState<MovieDetailPage> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        unawaited(
          ref.read(movieDetailControllerProvider.notifier).load(widget.movieId),
        );
      }
    });
  }

  @override
  void didUpdateWidget(MovieDetailPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.movieId != widget.movieId) {
      unawaited(
        ref.read(movieDetailControllerProvider.notifier).load(widget.movieId),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(movieDetailControllerProvider);
    if (state.status == MovieDetailStatus.idle ||
        state.status == MovieDetailStatus.loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (state.status == MovieDetailStatus.failed) {
      return _DetailFailure(
        notFound: state.isNotFound,
        onBack: widget.onBack,
        onRetry:
            () => unawaited(
              ref.read(movieDetailControllerProvider.notifier).retry(),
            ),
      );
    }
    final detail = state.detail!;
    return LayoutBuilder(
      builder: (context, constraints) {
        final narrow = constraints.maxWidth < 900;
        final horizontalPadding = narrow ? 16.0 : 24.0;
        return SingleChildScrollView(
          key: const ValueKey('movie-detail-scroll'),
          padding: EdgeInsets.fromLTRB(
            horizontalPadding,
            20,
            horizontalPadding,
            32,
          ),
          child: Align(
            alignment: Alignment.topLeft,
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 1280),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (narrow)
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        _cover(detail, narrow: true),
                        const SizedBox(height: 20),
                        _information(context, state, detail),
                      ],
                    )
                  else
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        _cover(detail, narrow: false),
                        const SizedBox(width: 24),
                        Expanded(child: _information(context, state, detail)),
                      ],
                    ),
                  const SizedBox(height: 28),
                  Column(
                    key: const ValueKey('movie-detail-sources-section'),
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _sectionTitle(context, '来源 ${detail.sourceCount}'),
                      const SizedBox(height: 8),
                      SourceList(
                        sources: detail.sources,
                        selectedSourceId: state.selectedSourceId,
                        onSelected:
                            ref
                                .read(movieDetailControllerProvider.notifier)
                                .selectSource,
                      ),
                    ],
                  ),
                  const SizedBox(height: 28),
                  Column(
                    key: const ValueKey('movie-detail-description-section'),
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _sectionTitle(context, '简介'),
                      const SizedBox(height: 8),
                      Text(
                        _descriptionText(detail),
                      ),
                    ],
                  ),
                  const SizedBox(height: 28),
                  Column(
                    key: const ValueKey('movie-detail-plot-section'),
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _sectionTitle(context, '剧照'),
                      const SizedBox(height: 10),
                      _PlotGrid(
                        urls: detail.plotImageUrls,
                        loader:
                            ref
                                .read(movieDetailGatewayProvider)
                                .loadCatalogImage,
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  String _descriptionText(MovieDetailDto detail) {
    final translated = detail.description?.trim();
    if (translated != null && translated.isNotEmpty) {
      return translated;
    }
    final original = detail.descriptionOriginal?.trim();
    if (original != null && original.isNotEmpty) {
      return '$original（原文）';
    }
    return '暂无简介';
  }

  Widget _cover(MovieDetailDto detail, {required bool narrow}) => SizedBox(
    key: const ValueKey('movie-detail-cover'),
    width: narrow ? 200 : 240,
    height: narrow ? 300 : 360,
    child: ClipRRect(
      borderRadius: BorderRadius.circular(6),
      child: _CatalogImage(
        url: detail.coverUrl,
        loader: ref.read(movieDetailGatewayProvider).loadCatalogImage,
        fit: BoxFit.cover,
        missingLabel: '暂无封面',
      ),
    ),
  );

  Widget _information(
    BuildContext context,
    MovieDetailState state,
    MovieDetailDto detail,
  ) {
    final liveProgress = freshestLivePlaybackProgress(
      ref.watch(
        livePlaybackProgressProvider.select((items) => items[detail.id]),
      ),
      detail.progress?.version,
    );
    final completed =
        liveProgress?.completed ?? detail.progress?.completed ?? false;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (widget.onBack != null) ...[
              IconButton(
                onPressed: widget.onBack,
                tooltip: '返回媒体库',
                icon: const Icon(Icons.arrow_back),
              ),
              const SizedBox(width: 4),
            ],
            Expanded(
              child: Text(
                detail.title,
                style: Theme.of(context).textTheme.headlineSmall,
              ),
            ),
            if (!detail.isLimited)
              SizedBox.square(
                dimension: 48,
                child: IconButton(
                  onPressed:
                      state.isFavoriteInFlight
                          ? null
                          : () => unawaited(
                            ref
                                .read(movieDetailControllerProvider.notifier)
                                .setFavorite(enabled: !detail.favorite),
                          ),
                  tooltip: detail.favorite ? '取消收藏影片' : '收藏影片',
                  icon: Icon(
                    detail.favorite ? Icons.favorite : Icons.favorite_border,
                  ),
                ),
              ),
          ],
        ),
        if (detail.isLimited) ...[
          const SizedBox(height: 8),
          _MetadataStatus(detail: detail),
        ],
        if (_isDistinct(detail.titleOriginal, detail.title)) ...[
          const SizedBox(height: 4),
          Text(
            detail.titleOriginal!,
            style: Theme.of(context).textTheme.titleMedium,
          ),
        ],
        const SizedBox(height: 10),
        Text(detail.number, style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 12),
        Wrap(
          spacing: 14,
          runSpacing: 8,
          children: [
            _Metadata('日期', detail.releaseDate ?? detail.publishDate ?? '未知'),
            _Metadata('厂商', detail.maker ?? '未知'),
            _Metadata('系列', detail.series ?? '未知'),
            _Metadata('导演', detail.director ?? '未知'),
            _Metadata('评分', detail.score?.toString() ?? '未知'),
          ],
        ),
        const SizedBox(height: 16),
        _sectionTitle(context, '演员'),
        const SizedBox(height: 6),
        detail.actors.isEmpty
            ? const Text('暂无演员')
            : Wrap(
              spacing: 8,
              runSpacing: 6,
              children: [
                for (final actor in detail.actors)
                  TextButton(
                    onPressed:
                        widget.onOpenActor == null
                            ? null
                            : () => widget.onOpenActor!(actor.id),
                    child: Text(actor.displayName),
                  ),
              ],
            ),
        const SizedBox(height: 12),
        _sectionTitle(context, '标签'),
        const SizedBox(height: 6),
        detail.tags.isEmpty
            ? const Text('暂无标签')
            : Wrap(
              spacing: 8,
              runSpacing: 6,
              children: [for (final tag in detail.tags) Chip(label: Text(tag))],
            ),
        if (state.favoriteErrorCode != null) ...[
          const SizedBox(height: 8),
          Text(
            '收藏更新失败，请重试',
            style: TextStyle(color: Theme.of(context).colorScheme.error),
          ),
        ],
        const SizedBox(height: 18),
        Wrap(
          spacing: 12,
          runSpacing: 10,
          children: [
            SizedBox(
              width: 220,
              height: 44,
              child: FilledButton.icon(
                key: const ValueKey('movie-detail-play'),
                onPressed:
                    state.selectedSourceId != null &&
                            widget.onPlaySource != null
                        ? () => ref
                            .read(movieDetailControllerProvider.notifier)
                            .playSelected(widget.onPlaySource)
                        : null,
                icon: Icon(
                  completed ? Icons.check_circle_outline : Icons.play_arrow,
                ),
                label: Text(
                  liveProgress == null
                      ? movieProgressLabel(detail.progress)
                      : liveMovieProgressLabel(liveProgress),
                ),
              ),
            ),
            SizedBox(
              width: 180,
              height: 44,
              child: OutlinedButton.icon(
                key: const ValueKey('movie-detail-rescrape'),
                onPressed:
                    state.isRescrapeInFlight
                        ? null
                        : () => unawaited(
                          ref
                              .read(movieDetailControllerProvider.notifier)
                              .rescrape(),
                        ),
                icon: const Icon(Icons.refresh),
                label: Text(state.isRescrapeInFlight ? '提交中...' : '重新刮削'),
              ),
            ),
          ],
        ),
        if (_rescrapeMessage(state) case final message?) ...[
          const SizedBox(height: 8),
          Text(
            message,
            key: const ValueKey('movie-detail-rescrape-message'),
            style:
                state.rescrapeErrorCode == null
                    ? null
                    : TextStyle(color: Theme.of(context).colorScheme.error),
          ),
        ],
      ],
    );
  }
}

class _MetadataStatus extends StatelessWidget {
  const _MetadataStatus({required this.detail});

  final MovieDetailDto detail;

  @override
  Widget build(BuildContext context) {
    final label = switch (detail.metadataState) {
      MovieMetadataState.coreReady => '',
      MovieMetadataState.queued => '资料排队中',
      MovieMetadataState.running => '正在补全资料',
      MovieMetadataState.failed => '资料补全失败',
    };
    final error = switch (detail.metadataErrorCode) {
      'javdb_movie_not_found' => 'JavDB 未找到该番号',
      'metadata_timeout' => '元数据刮削超时',
      null => null,
      _ => '请在诊断页查看失败原因',
    };
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(
          detail.metadataState == MovieMetadataState.failed
              ? Icons.error_outline
              : Icons.hourglass_top,
          size: 18,
          color:
              detail.metadataState == MovieMetadataState.failed
                  ? Theme.of(context).colorScheme.error
                  : null,
        ),
        const SizedBox(width: 8),
        Expanded(child: Text(error == null ? label : '$label：$error')),
      ],
    );
  }
}

class _Metadata extends StatelessWidget {
  const _Metadata(this.label, this.value);

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => SizedBox(
    width: 150,
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: Theme.of(context).textTheme.labelSmall),
        Text(value, maxLines: 2, overflow: TextOverflow.ellipsis),
      ],
    ),
  );
}

class _PlotGrid extends StatelessWidget {
  const _PlotGrid({required this.urls, required this.loader});

  final List<String> urls;
  final Future<List<int>> Function(String) loader;

  @override
  Widget build(BuildContext context) {
    if (urls.isEmpty) return const Text('暂无剧照');
    return LayoutBuilder(
      builder: (context, constraints) {
        final columns = ((constraints.maxWidth + 12) / (220 + 12))
            .floor()
            .clamp(1, 100);
        return GridView.builder(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          itemCount: urls.length,
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: columns,
            childAspectRatio: 16 / 9,
            crossAxisSpacing: 12,
            mainAxisSpacing: 12,
          ),
          itemBuilder:
              (context, index) => _CatalogImage(
                url: urls[index],
                loader: loader,
                fit: BoxFit.cover,
                missingLabel: '剧照加载失败',
              ),
        );
      },
    );
  }
}

class _CatalogImage extends StatefulWidget {
  const _CatalogImage({
    required this.url,
    required this.loader,
    required this.fit,
    required this.missingLabel,
  });

  final String? url;
  final Future<List<int>> Function(String) loader;
  final BoxFit fit;
  final String missingLabel;

  @override
  State<_CatalogImage> createState() => _CatalogImageState();
}

class _CatalogImageState extends State<_CatalogImage> {
  Future<List<int>>? _future;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(_CatalogImage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.url != widget.url || oldWidget.loader != widget.loader) {
      _load();
    }
  }

  void _load() {
    _future = widget.url == null ? null : widget.loader(widget.url!);
  }

  @override
  Widget build(BuildContext context) {
    final future = _future;
    if (future == null) return _placeholder(context);
    return FutureBuilder<List<int>>(
      future: future,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator(strokeWidth: 2));
        }
        if (snapshot.hasError || snapshot.data == null) {
          return _placeholder(context);
        }
        return Image.memory(
          Uint8List.fromList(snapshot.data!),
          fit: widget.fit,
          errorBuilder: (context, error, stackTrace) => _placeholder(context),
        );
      },
    );
  }

  Widget _placeholder(BuildContext context) => ColoredBox(
    color: Theme.of(context).colorScheme.surfaceContainerHigh,
    child: Center(child: Text(widget.missingLabel)),
  );
}

class _DetailFailure extends StatelessWidget {
  const _DetailFailure({
    required this.notFound,
    required this.onBack,
    required this.onRetry,
  });

  final bool notFound;
  final VoidCallback? onBack;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => Center(
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(notFound ? '影片资料不存在' : '影片详情加载失败'),
        const SizedBox(height: 12),
        if (!notFound)
          FilledButton(onPressed: onRetry, child: const Text('重试')),
        if (onBack != null)
          TextButton(onPressed: onBack, child: const Text('返回媒体库')),
      ],
    ),
  );
}

Widget _sectionTitle(BuildContext context, String label) =>
    Text(label, style: Theme.of(context).textTheme.titleMedium);

bool _isDistinct(String? value, String? primary) =>
    value != null && value.trim().isNotEmpty && value.trim() != primary?.trim();

String? _rescrapeMessage(MovieDetailState state) {
  if (state.rescrapeErrorCode != null) {
    return switch (state.rescrapeErrorCode) {
      'metadata_job_already_active' => '已有富化任务正在执行，请完成后再试',
      'resource_not_found' => '影片资料不存在',
      'client_transport_error' => '无法连接服务器，请稍后重试',
      _ => '重新刮削失败，请重试',
    };
  }
  return switch (state.rescrapeState) {
    MetadataRescrapeState.queued => '已加入最高优先级刮削队列',
    MetadataRescrapeState.running => '当前番号正在刮削',
    null => null,
  };
}

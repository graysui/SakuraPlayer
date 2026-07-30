import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/features/library/data/movies_api.dart';
import 'package:sakuraplayer_windows/features/library/presentation/movie_card.dart';
import 'package:sakuraplayer_windows/features/rankings/data/rankings_api.dart';
import 'package:sakuraplayer_windows/features/rankings/presentation/rankings_controller.dart';

class RankingsPage extends ConsumerStatefulWidget {
  const RankingsPage({
    required this.onOpenSettings,
    this.onOpenMovie,
    super.key,
  });

  final VoidCallback onOpenSettings;
  final ValueChanged<String>? onOpenMovie;

  @override
  ConsumerState<RankingsPage> createState() => _RankingsPageState();
}

class _RankingsPageState extends ConsumerState<RankingsPage> {
  final ScrollController _scrollController = ScrollController();

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        unawaited(ref.read(rankingsControllerProvider.notifier).ensureLoaded());
      }
    });
  }

  @override
  void dispose() {
    _scrollController
      ..removeListener(_onScroll)
      ..dispose();
    super.dispose();
  }

  void _onScroll() {
    if (!_scrollController.hasClients) return;
    final position = _scrollController.position;
    if (position.maxScrollExtent - position.pixels <= 480) {
      unawaited(ref.read(rankingsControllerProvider.notifier).loadMore());
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(rankingsControllerProvider);
    return LayoutBuilder(
      builder: (context, constraints) {
        final horizontalPadding = constraints.maxWidth < 900 ? 16.0 : 24.0;
        final gridWidth = constraints.maxWidth - horizontalPadding * 2;
        final columns = ((gridWidth + 16) / (184 + 16)).floor().clamp(1, 100);
        return CustomScrollView(
          controller: _scrollController,
          slivers: [
            SliverPadding(
              padding: EdgeInsets.fromLTRB(
                horizontalPadding,
                20,
                horizontalPadding,
                16,
              ),
              sliver: SliverToBoxAdapter(
                child: _Header(
                  state: state,
                  onBoardChanged: _selectBoard,
                  onYearChanged: _selectYear,
                  onRefresh:
                      () => unawaited(
                        ref.read(rankingsControllerProvider.notifier).refresh(),
                      ),
                ),
              ),
            ),
            ..._contentSlivers(context, state, horizontalPadding, columns),
          ],
        );
      },
    );
  }

  List<Widget> _contentSlivers(
    BuildContext context,
    RankingsState state,
    double horizontalPadding,
    int columns,
  ) {
    if (state.status == RankingsStatus.idle ||
        state.status == RankingsStatus.loading) {
      return const [
        SliverFillRemaining(
          hasScrollBody: false,
          child: Center(child: CircularProgressIndicator()),
        ),
      ];
    }
    if (state.status == RankingsStatus.failed) {
      return [
        SliverFillRemaining(
          hasScrollBody: false,
          child: _MessageState(
            icon: Icons.cloud_off_outlined,
            title: '排行榜加载失败',
            actionLabel: '重试',
            onAction:
                () => unawaited(
                  ref.read(rankingsControllerProvider.notifier).retryInitial(),
                ),
          ),
        ),
      ];
    }
    if (state.status == RankingsStatus.unavailable) {
      final reason = state.unavailableReason!;
      final opensSettings =
          reason == RankingUnavailableReason.credentialsNotConfigured ||
          reason == RankingUnavailableReason.credentialsInvalid;
      return [
        SliverFillRemaining(
          hasScrollBody: false,
          child: _MessageState(
            icon:
                opensSettings
                    ? Icons.key_off_outlined
                    : Icons.leaderboard_outlined,
            title: _unavailableTitle(reason),
            actionLabel: opensSettings ? '前往设置' : '重新加载',
            onAction:
                opensSettings
                    ? widget.onOpenSettings
                    : () => unawaited(
                      ref
                          .read(rankingsControllerProvider.notifier)
                          .retryInitial(),
                    ),
          ),
        ),
      ];
    }
    final slivers = <Widget>[];
    if (state.isRefreshing) {
      slivers.add(
        SliverPadding(
          padding: EdgeInsets.symmetric(horizontal: horizontalPadding),
          sliver: const SliverToBoxAdapter(child: LinearProgressIndicator()),
        ),
      );
    } else if (state.refreshErrorCode != null) {
      slivers.add(
        SliverPadding(
          padding: EdgeInsets.fromLTRB(
            horizontalPadding,
            0,
            horizontalPadding,
            12,
          ),
          sliver: SliverToBoxAdapter(
            child: _RefreshError(
              onRetry:
                  () => unawaited(
                    ref.read(rankingsControllerProvider.notifier).refresh(),
                  ),
            ),
          ),
        ),
      );
    }
    if (state.items.isEmpty) {
      slivers.add(
        const SliverFillRemaining(
          hasScrollBody: false,
          child: Center(child: Text('当前榜单暂无可展示影片')),
        ),
      );
      return slivers;
    }
    final coverLoader = ref.read(moviesGatewayProvider).loadCover;
    slivers.add(
      SliverPadding(
        padding: EdgeInsets.fromLTRB(
          horizontalPadding,
          0,
          horizontalPadding,
          20,
        ),
        sliver: SliverGrid(
          key: const ValueKey('rankings-grid'),
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: columns,
            mainAxisExtent: 408,
            crossAxisSpacing: 16,
            mainAxisSpacing: 16,
          ),
          delegate: SliverChildBuilderDelegate((context, index) {
            final item = state.items[index];
            return Stack(
              key: ValueKey('ranking-${item.rank}-${item.movie.id}'),
              children: [
                Positioned.fill(
                  child: MovieCard(
                    movie: item.movie,
                    coverLoader: coverLoader,
                    onOpen:
                        widget.onOpenMovie == null
                            ? null
                            : () => widget.onOpenMovie!(item.movie.id),
                  ),
                ),
                Positioned(left: 8, top: 8, child: _RankBadge(rank: item.rank)),
              ],
            );
          }, childCount: state.items.length),
        ),
      ),
    );
    slivers.add(
      SliverToBoxAdapter(
        child: SizedBox(
          height: 64,
          child: Center(
            child:
                state.isAppending
                    ? const SizedBox.square(
                      dimension: 24,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                    : state.appendErrorCode != null
                    ? Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Text('加载更多失败'),
                        const SizedBox(width: 8),
                        TextButton(
                          onPressed:
                              () => unawaited(
                                ref
                                    .read(rankingsControllerProvider.notifier)
                                    .retryAppend(),
                              ),
                          child: const Text('重试加载'),
                        ),
                      ],
                    )
                    : null,
          ),
        ),
      ),
    );
    return slivers;
  }

  void _selectBoard(RankingBoard board) {
    _jumpToTop();
    unawaited(ref.read(rankingsControllerProvider.notifier).selectBoard(board));
  }

  void _selectYear(int? year) {
    _jumpToTop();
    unawaited(ref.read(rankingsControllerProvider.notifier).selectYear(year));
  }

  void _jumpToTop() {
    if (_scrollController.hasClients) _scrollController.jumpTo(0);
  }
}

class _Header extends StatelessWidget {
  const _Header({
    required this.state,
    required this.onBoardChanged,
    required this.onYearChanged,
    required this.onRefresh,
  });

  final RankingsState state;
  final ValueChanged<RankingBoard> onBoardChanged;
  final ValueChanged<int?> onYearChanged;
  final VoidCallback onRefresh;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                '排行榜',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
            ),
            IconButton(
              onPressed:
                  state.status == RankingsStatus.idle ||
                          state.status == RankingsStatus.loading ||
                          state.isRefreshing
                      ? null
                      : onRefresh,
              tooltip: '刷新排行榜',
              icon: const Icon(Icons.refresh),
            ),
          ],
        ),
        const SizedBox(height: 12),
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: SegmentedButton<RankingBoard>(
            showSelectedIcon: false,
            segments: const [
              ButtonSegment(value: RankingBoard.daily, label: Text('日榜')),
              ButtonSegment(value: RankingBoard.weekly, label: Text('周榜')),
              ButtonSegment(value: RankingBoard.monthly, label: Text('月榜')),
              ButtonSegment(value: RankingBoard.top250, label: Text('TOP250')),
            ],
            selected: <RankingBoard>{state.selection.board},
            onSelectionChanged: (selection) => onBoardChanged(selection.single),
          ),
        ),
        if (state.selection.board == RankingBoard.top250) ...[
          const SizedBox(height: 12),
          DropdownButtonHideUnderline(
            child: DropdownButton<String>(
              key: const ValueKey('ranking-year-selector'),
              value: state.selection.year?.toString() ?? 'overall',
              items: [
                const DropdownMenuItem(value: 'overall', child: Text('总榜')),
                for (final year in state.availableYears)
                  DropdownMenuItem(
                    value: year.toString(),
                    child: Text(year.toString()),
                  ),
              ],
              onChanged: (value) {
                if (value == null) return;
                onYearChanged(value == 'overall' ? null : int.parse(value));
              },
            ),
          ),
        ],
        if (state.syncedAt != null) ...[
          const SizedBox(height: 10),
          Text(
            '快照更新：${_formatDateTime(state.syncedAt!)}',
            key: const ValueKey('ranking-synced-at'),
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ],
    );
  }
}

class _RankBadge extends StatelessWidget {
  const _RankBadge({required this.rank});

  final int rank;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: colors.primaryContainer.withValues(alpha: 0.94),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        child: Text(
          '#$rank',
          style: Theme.of(context).textTheme.labelMedium?.copyWith(
            color: colors.onPrimaryContainer,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
    );
  }
}

class _RefreshError extends StatelessWidget {
  const _RefreshError({required this.onRetry});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return ColoredBox(
      color: colors.errorContainer,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        child: Row(
          children: [
            Icon(Icons.sync_problem, color: colors.onErrorContainer),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                '刷新失败，仍显示上次快照',
                style: TextStyle(color: colors.onErrorContainer),
              ),
            ),
            TextButton(onPressed: onRetry, child: const Text('重试刷新')),
          ],
        ),
      ),
    );
  }
}

class _MessageState extends StatelessWidget {
  const _MessageState({
    required this.icon,
    required this.title,
    required this.actionLabel,
    required this.onAction,
  });

  final IconData icon;
  final String title;
  final String actionLabel;
  final VoidCallback onAction;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 40),
            const SizedBox(height: 12),
            Text(title, textAlign: TextAlign.center),
            const SizedBox(height: 12),
            FilledButton(onPressed: onAction, child: Text(actionLabel)),
          ],
        ),
      ),
    );
  }
}

String _unavailableTitle(RankingUnavailableReason reason) => switch (reason) {
  RankingUnavailableReason.credentialsNotConfigured => 'TOP250 尚未配置 JavDB 凭据',
  RankingUnavailableReason.credentialsInvalid => 'JavDB 凭据已失效',
  RankingUnavailableReason.neverSynced => '当前榜单尚未生成快照',
  RankingUnavailableReason.syncFailed => '当前榜单同步失败，暂无可用快照',
};

String _formatDateTime(DateTime value) {
  final local = value.toLocal();
  String two(int part) => part.toString().padLeft(2, '0');
  return '${local.year}-${two(local.month)}-${two(local.day)} '
      '${two(local.hour)}:${two(local.minute)}';
}

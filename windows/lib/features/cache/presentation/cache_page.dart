import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/features/cache/data/cache_api.dart';
import 'package:sakuraplayer_windows/features/cache/presentation/cache_controller.dart';

class CachePage extends ConsumerStatefulWidget {
  const CachePage({super.key, this.onPlay});

  final void Function(String cacheJobId, String mediaId)? onPlay;

  @override
  ConsumerState<CachePage> createState() => _CachePageState();
}

class _CachePageState extends ConsumerState<CachePage> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) ref.read(cacheControllerProvider.notifier).loadInitial();
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(cacheControllerProvider);
    return LayoutBuilder(
      builder: (context, constraints) {
        final horizontal = constraints.maxWidth < 900 ? 16.0 : 24.0;
        return Align(
          alignment: Alignment.topLeft,
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1280),
            child: RefreshIndicator(
              onRefresh: ref.read(cacheControllerProvider.notifier).refresh,
              child: ListView(
                key: const ValueKey('cache-page-list'),
                padding: EdgeInsets.fromLTRB(horizontal, 20, horizontal, 32),
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          '缓存管理',
                          style: Theme.of(context).textTheme.headlineSmall,
                        ),
                      ),
                      IconButton(
                        onPressed:
                            state.status == CachePageStatus.loading
                                ? null
                                : ref
                                    .read(cacheControllerProvider.notifier)
                                    .refresh,
                        tooltip: '刷新缓存任务',
                        icon: const Icon(Icons.refresh),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  _CapacitySummary(
                    capacity: state.capacity,
                    narrow: constraints.maxWidth < 640,
                  ),
                  const SizedBox(height: 20),
                  if (state.status == CachePageStatus.loading)
                    const Center(
                      child: Padding(
                        padding: EdgeInsets.all(32),
                        child: CircularProgressIndicator(),
                      ),
                    )
                  else if (state.status == CachePageStatus.failed)
                    _ErrorPanel(
                      code: state.errorCode,
                      onRetry:
                          ref
                              .read(cacheControllerProvider.notifier)
                              .loadInitial,
                    )
                  else if (state.items.isEmpty)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 48),
                      child: Center(child: Text('暂无缓存任务')),
                    )
                  else
                    ...state.items.map(
                      (job) => _CacheJobRow(job: job, onPlay: widget.onPlay),
                    ),
                  if (state.nextCursor != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 12),
                      child: OutlinedButton.icon(
                        onPressed:
                            state.isAppending
                                ? null
                                : ref
                                    .read(cacheControllerProvider.notifier)
                                    .loadMore,
                        icon:
                            state.isAppending
                                ? const SizedBox.square(
                                  dimension: 18,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                  ),
                                )
                                : const Icon(Icons.expand_more),
                        label: const Text('加载更多'),
                      ),
                    ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

class _CapacitySummary extends StatelessWidget {
  const _CapacitySummary({required this.capacity, required this.narrow});
  final CacheCapacityDto? capacity;
  final bool narrow;
  @override
  Widget build(BuildContext context) {
    final values = <(String, int, int, IconData)>[
      ('运行', capacity?.running ?? 0, 2, Icons.sync),
      ('排队', capacity?.queued ?? 0, 10, Icons.schedule),
      ('就绪', capacity?.ready ?? 0, 20, Icons.check_circle_outline),
    ];
    final children = values
        .map(
          (value) => Container(
            key: ValueKey('capacity-${value.$1}'),
            height: 82,
            padding: const EdgeInsets.symmetric(horizontal: 16),
            decoration: BoxDecoration(
              border: Border.all(
                color: Theme.of(context).colorScheme.outlineVariant,
              ),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Row(
              children: [
                Icon(value.$4),
                const SizedBox(width: 12),
                Expanded(child: Text(value.$1)),
                Text(
                  '${value.$2} / ${value.$3}',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ],
            ),
          ),
        )
        .toList(growable: false);
    return narrow
        ? Column(
          children: [
            for (final child in children) ...[child, const SizedBox(height: 8)],
          ],
        )
        : Row(
          children: [
            for (final child in children) ...[
              Expanded(child: child),
              if (child != children.last) const SizedBox(width: 10),
            ],
          ],
        );
  }
}

class _CacheJobRow extends ConsumerWidget {
  const _CacheJobRow({required this.job, required this.onPlay});

  final CacheJobDto job;
  final void Function(String cacheJobId, String mediaId)? onPlay;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(cacheControllerProvider);
    final busy = state.inFlightIds.contains(job.id);
    final error = state.actionErrors[job.id];
    return Container(
      key: ValueKey('cache-job-${job.id}'),
      constraints: const BoxConstraints(minHeight: 96),
      padding: const EdgeInsets.symmetric(vertical: 12),
      decoration: BoxDecoration(
        border: Border(
          bottom: BorderSide(
            color: Theme.of(context).colorScheme.outlineVariant,
          ),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              SizedBox(
                width: 128,
                child: Text(
                  cacheStatusLabels[job.status]!,
                  style: Theme.of(context).textTheme.labelLarge,
                ),
              ),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '任务 ${job.id.substring(0, 8)}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 6),
                    LinearProgressIndicator(value: job.remotePercent / 100),
                    if (job.errorCode != null || error != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 6),
                        child: Text(
                          _cacheErrorLabel(error ?? job.errorCode!),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            color: Theme.of(context).colorScheme.error,
                          ),
                        ),
                      ),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              if (busy)
                const SizedBox.square(
                  dimension: 24,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              else if (canCancelCacheStatus(job.status))
                IconButton(
                  onPressed:
                      () => _confirm(
                        context,
                        title: '取消缓存任务？',
                        message: '任务将停止并进入安全清理。',
                        action:
                            () => ref
                                .read(cacheControllerProvider.notifier)
                                .cancel(job.id, confirmed: true),
                      ),
                  tooltip: '取消任务',
                  icon: const Icon(Icons.cancel_outlined),
                )
              else if (job.status == 'ready' && job.selectedMediaIds.isNotEmpty)
                IconButton(
                  onPressed:
                      onPlay == null
                          ? null
                          : () => onPlay!(job.id, job.selectedMediaIds.first),
                  tooltip: '播放缓存',
                  icon: const Icon(Icons.play_arrow),
                ),
              if (!busy && canCleanupCacheStatus(job.status))
                IconButton(
                  onPressed:
                      () => _confirm(
                        context,
                        title: '清理缓存？',
                        message: '仅删除应用管理目录中的已验证文件。',
                        action:
                            () => ref
                                .read(cacheControllerProvider.notifier)
                                .cleanup(job.id, confirmed: true),
                      ),
                  tooltip: '清理缓存',
                  color: Theme.of(context).colorScheme.error,
                  icon: const Icon(Icons.delete_outline),
                ),
            ],
          ),
          if (job.status == 'awaiting_selection')
            _CandidateSelector(job: job, enabled: !busy, onPlay: onPlay),
        ],
      ),
    );
  }
}

class _CandidateSelector extends ConsumerWidget {
  const _CandidateSelector({
    required this.job,
    required this.enabled,
    required this.onPlay,
  });

  final CacheJobDto job;
  final bool enabled;
  final void Function(String cacheJobId, String mediaId)? onPlay;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final groups = validMediaCandidateGroups(job);
    if (groups.isEmpty) {
      return const Padding(
        padding: EdgeInsets.only(top: 10),
        child: Text('没有可选择的有效媒体文件'),
      );
    }
    return Padding(
      padding: const EdgeInsets.only(top: 10, left: 128),
      child: Wrap(
        spacing: 8,
        runSpacing: 8,
        children: [
          for (final group in groups)
            FilledButton.icon(
              key: ValueKey('select-candidate-${group.id}'),
              onPressed:
                  !enabled
                      ? null
                      : () async {
                        final result = await ref
                            .read(cacheControllerProvider.notifier)
                            .selectMedia(job.id, group);
                        if (context.mounted && result != null) {
                          onPlay?.call(
                            result.id,
                            result.selectedMediaIds.first,
                          );
                        }
                      },
              icon: const Icon(Icons.play_arrow),
              label: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 360),
                child: Text(
                  '选择并播放 ${group.label}',
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ),
        ],
      ),
    );
  }
}

Future<void> _confirm(
  BuildContext context, {
  required String title,
  required String message,
  required Future<void> Function() action,
}) async {
  final confirmed =
      await showDialog<bool>(
        context: context,
        builder:
            (context) => AlertDialog(
              title: Text(title),
              content: Text(message),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(context, false),
                  child: const Text('返回'),
                ),
                FilledButton(
                  onPressed: () => Navigator.pop(context, true),
                  child: const Text('确认'),
                ),
              ],
            ),
      ) ??
      false;
  if (confirmed) await action();
}

class _ErrorPanel extends StatelessWidget {
  const _ErrorPanel({required this.code, required this.onRetry});
  final String? code;
  final VoidCallback onRetry;
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 32),
    child: Column(
      children: [
        Text(code ?? '加载失败'),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          onPressed: onRetry,
          icon: const Icon(Icons.refresh),
          label: const Text('重试'),
        ),
      ],
    ),
  );
}

String _cacheErrorLabel(String code) => switch (code) {
  'cache_active_lease' => '缓存正在播放，暂时不能清理',
  'cache_ownership_mismatch' => '缓存目录归属不一致，任务已失联',
  'cloud115_credentials_expired' => '115 凭据已失效，请重新扫码',
  'cloud115_unavailable' => '115 暂时不可用，请稍后重试',
  _ => code,
};

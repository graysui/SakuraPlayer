import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/features/settings/data/settings_api.dart';
import 'package:sakuraplayer_windows/features/settings/presentation/settings_controller.dart';

class DiagnosticsPage extends ConsumerStatefulWidget {
  const DiagnosticsPage({this.onBack, super.key});
  final VoidCallback? onBack;
  @override
  ConsumerState<DiagnosticsPage> createState() => _DiagnosticsPageState();
}

class _DiagnosticsPageState extends ConsumerState<DiagnosticsPage> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) ref.read(diagnosticsControllerProvider.notifier).load();
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(diagnosticsControllerProvider);
    return LayoutBuilder(
      builder: (context, constraints) {
        final horizontal = constraints.maxWidth < 900 ? 16.0 : 24.0;
        return Align(
          alignment: Alignment.topLeft,
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1280),
            child: ListView(
              padding: EdgeInsets.fromLTRB(horizontal, 16, horizontal, 32),
              children: [
                Row(
                  children: [
                    IconButton(
                      onPressed: widget.onBack,
                      tooltip: '返回设置',
                      icon: const Icon(Icons.arrow_back),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        '诊断与任务',
                        style: Theme.of(context).textTheme.headlineSmall,
                      ),
                    ),
                    IconButton(
                      onPressed:
                          state.status == DiagnosticsStatus.loading
                              ? null
                              : ref
                                  .read(diagnosticsControllerProvider.notifier)
                                  .load,
                      tooltip: '刷新诊断',
                      icon: const Icon(Icons.refresh),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                if (state.status == DiagnosticsStatus.loading)
                  const Center(
                    child: Padding(
                      padding: EdgeInsets.all(32),
                      child: CircularProgressIndicator(),
                    ),
                  )
                else if (state.status == DiagnosticsStatus.failed)
                  _Message(code: state.errorCode)
                else if (state.diagnostics != null) ...[
                  Text('生成时间：${_formatTime(state.diagnostics!.generatedAt)}'),
                  const SizedBox(height: 8),
                  _Components(diagnostics: state.diagnostics!),
                  const SizedBox(height: 24),
                  Text('连接测试', style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 8),
                  if (state.diagnostics!.connectionTests.isEmpty)
                    const Text('暂无连接测试')
                  else
                    ...state.diagnostics!.connectionTests.map(
                      (item) => ListTile(
                        contentPadding: EdgeInsets.zero,
                        title: Text('${item.target} · ${item.status}'),
                        subtitle: Text(
                          '${item.elapsedMs} ms · ${item.errorCode ?? '无错误'} · ${_formatTime(item.checkedAt)}',
                        ),
                      ),
                    ),
                  const SizedBox(height: 24),
                  Text('最近失败', style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 8),
                  if (state.diagnostics!.recentFailures.isEmpty)
                    const Text('暂无失败记录')
                  else
                    ...state.diagnostics!.recentFailures.map(
                      (item) => ListTile(
                        contentPadding: EdgeInsets.zero,
                        leading: const Icon(Icons.error_outline),
                        title: Text('${item.taskType} · ${item.errorCode}'),
                        subtitle: Text(
                          '${item.stage ?? '无阶段'} · 第 ${item.attemptNo} 次 · ${item.elapsedMs == null ? '耗时未知' : '${item.elapsedMs} ms'} · ${_formatTime(item.occurredAt)}',
                        ),
                      ),
                    ),
                  const SizedBox(height: 24),
                  Text('元数据任务', style: Theme.of(context).textTheme.titleMedium),
                  ...state.jobs.map((job) => _MetadataRow(job: job)),
                  if (state.nextCursor != null)
                    OutlinedButton.icon(
                      onPressed:
                          state.isAppending
                              ? null
                              : ref
                                  .read(diagnosticsControllerProvider.notifier)
                                  .loadMore,
                      icon: const Icon(Icons.expand_more),
                      label: const Text('加载更多'),
                    ),
                ],
              ],
            ),
          ),
        );
      },
    );
  }
}

class _Components extends StatelessWidget {
  const _Components({required this.diagnostics});
  final DiagnosticsDto diagnostics;
  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text('组件状态', style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: 8),
      Wrap(
        spacing: 16,
        runSpacing: 8,
        children:
            diagnostics.components
                .map(
                  (item) => SizedBox(
                    width: 210,
                    child: Row(
                      children: [
                        Icon(
                          item.status == 'healthy'
                              ? Icons.check_circle_outline
                              : Icons.info_outline,
                          size: 18,
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            '${item.component} · ${item.status} · ${item.errorCode ?? '无错误'} · ${_formatTime(item.checkedAt)}',
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ],
                    ),
                  ),
                )
                .toList(),
      ),
      const SizedBox(height: 16),
      Text(
        '队列：元数据 ${diagnostics.queues.metadataQueued} / ${diagnostics.queues.metadataRunning}，缓存 ${diagnostics.queues.cacheQueued} / ${diagnostics.queues.cacheRunning} / ${diagnostics.queues.cacheReady}',
      ),
    ],
  );
}

class _MetadataRow extends ConsumerWidget {
  const _MetadataRow({required this.job});
  final MetadataJobDto job;
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final busy = ref
        .watch(diagnosticsControllerProvider)
        .inFlightIds
        .contains(job.id);
    final coreSucceeded = job.stages.any(
      (stage) => stage.stage == 'javdb_core' && stage.status == 'succeeded',
    );
    final canFull = job.status == 'failed' && !coreSucceeded;
    final retryable = job.retryableStages
        .where(enrichmentStages.contains)
        .toList(growable: false);
    return Container(
      constraints: const BoxConstraints(minHeight: 96),
      decoration: BoxDecoration(
        border: Border(
          bottom: BorderSide(
            color: Theme.of(context).colorScheme.outlineVariant,
          ),
        ),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(job.number, maxLines: 1, overflow: TextOverflow.ellipsis),
                Text(
                  '${job.status} · ${job.stage ?? '无阶段'} · 第 ${job.attemptNo} 次',
                  maxLines: 2,
                ),
                if (job.errorCode != null)
                  Text(
                    job.errorCode!,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
              ],
            ),
          ),
          if (busy)
            const SizedBox.square(
              dimension: 24,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          else if (canFull)
            IconButton(
              onPressed:
                  () => ref
                      .read(diagnosticsControllerProvider.notifier)
                      .retryFull(job.id),
              tooltip: '完整重试',
              icon: const Icon(Icons.replay),
            )
          else if (retryable.isNotEmpty)
            IconButton(
              onPressed: () => _chooseStages(context, ref, job, retryable),
              tooltip: '重试富化阶段',
              icon: const Icon(Icons.tune),
            ),
        ],
      ),
    );
  }
}

Future<void> _chooseStages(
  BuildContext context,
  WidgetRef ref,
  MetadataJobDto job,
  List<String> retryable,
) async {
  final selected = defaultEnrichmentSelection(retryable);
  final result = await showDialog<List<String>>(
    context: context,
    builder: (context) => _StageDialog(retryable: retryable, initial: selected),
  );
  if (result != null && result.isNotEmpty) {
    await ref
        .read(diagnosticsControllerProvider.notifier)
        .retryEnrichment(job.id, result);
  }
}

class _StageDialog extends StatefulWidget {
  const _StageDialog({required this.retryable, required this.initial});
  final List<String> retryable;
  final Set<String> initial;
  @override
  State<_StageDialog> createState() => _StageDialogState();
}

class _StageDialogState extends State<_StageDialog> {
  late final selected = {...widget.initial};
  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('选择富化阶段'),
    content: Column(
      mainAxisSize: MainAxisSize.min,
      children:
          widget.retryable
              .map(
                (stage) => CheckboxListTile(
                  value: selected.contains(stage),
                  title: Text(stage),
                  onChanged:
                      (value) => setState(() {
                        if (value ?? false) {
                          selected.add(stage);
                        } else {
                          selected.remove(stage);
                        }
                      }),
                ),
              )
              .toList(),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('取消'),
      ),
      FilledButton(
        onPressed:
            selected.isEmpty
                ? null
                : () => Navigator.pop(context, selected.toList()),
        child: const Text('重试'),
      ),
    ],
  );
}

class _Message extends StatelessWidget {
  const _Message({required this.code});
  final String? code;
  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: const EdgeInsets.all(32),
      child: Text(code ?? '诊断加载失败'),
    ),
  );
}

String _formatTime(DateTime value) =>
    value.toLocal().toIso8601String().replaceFirst('T', ' ').split('.').first;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/features/settings/data/settings_api.dart';
import 'package:sakuraplayer_windows/features/settings/presentation/settings_controller.dart';
import 'package:sakuraplayer_windows/features/settings/presentation/settings_labels.dart';

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
                else if (state.diagnostics != null)
                  ..._content(context, state.diagnostics!),
              ],
            ),
          ),
        );
      },
    );
  }

  List<Widget> _content(BuildContext context, DiagnosticsDto diagnostics) {
    final cacheFailures = diagnostics.recentFailures
        .where((item) => item.taskType == 'cache')
        .toList(growable: false);
    return [
      Text('生成时间：${_formatTime(diagnostics.generatedAt)}'),
      const SizedBox(height: 8),
      _Components(diagnostics: diagnostics),
      const SizedBox(height: 24),
      _MetadataProgress(progress: diagnostics.metadataProgress),
      const SizedBox(height: 24),
      Text('连接测试', style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: 8),
      if (diagnostics.connectionTests.isEmpty)
        const Text('暂无连接测试')
      else
        ...diagnostics.connectionTests.map(
          (item) => ListTile(
            contentPadding: EdgeInsets.zero,
            title: Text(
              '${settingsTargetLabel(item.target)} · ${settingsStatusLabel(item.status)}',
            ),
            subtitle: Text(
              '${item.elapsedMs} ms · ${settingsErrorLabel(item.errorCode)} · ${_formatTime(item.checkedAt)}',
            ),
          ),
        ),
      const SizedBox(height: 24),
      Text('缓存最近失败', style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: 8),
      if (cacheFailures.isEmpty)
        const Text('暂无失败记录')
      else
        ...cacheFailures.map(
          (item) => ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.error_outline),
            title: Text('缓存 · ${settingsErrorLabel(item.errorCode)}'),
            subtitle: Text(
              '${metadataStageLabel(item.stage)} · 第 ${item.attemptNo} 次 · ${item.elapsedMs == null ? '耗时未知' : '${item.elapsedMs} ms'} · ${_formatTime(item.occurredAt)}',
            ),
          ),
        ),
    ];
  }
}

class _MetadataProgress extends StatelessWidget {
  const _MetadataProgress({required this.progress});
  final MetadataProgressDto progress;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text('元数据刮削进度', style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: 12),
      LinearProgressIndicator(value: progress.fraction, minHeight: 8),
      const SizedBox(height: 8),
      Text('已处理 ${progress.finished} / ${progress.total}'),
      const SizedBox(height: 8),
      Text(
        progress.currentNumbers.isEmpty
            ? '当前刮削番号：暂无'
            : '当前刮削番号：${progress.currentNumbers.join('、')}',
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
      ),
    ],
  );
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
                    width: 240,
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
                            '${settingsTargetLabel(item.component)} · ${settingsStatusLabel(item.status)} · ${settingsErrorLabel(item.errorCode)}',
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
        '缓存队列：排队 ${diagnostics.queues.cacheQueued} · 运行 ${diagnostics.queues.cacheRunning} · 就绪 ${diagnostics.queues.cacheReady}',
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
      child: Text(code == null ? '诊断加载失败' : settingsErrorLabel(code)),
    ),
  );
}

String _formatTime(DateTime value) =>
    value.toLocal().toIso8601String().replaceFirst('T', ' ').split('.').first;

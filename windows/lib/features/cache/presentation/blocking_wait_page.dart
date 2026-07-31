import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/features/cache/presentation/play_request_controller.dart';

class BlockingWaitPage extends ConsumerStatefulWidget {
  const BlockingWaitPage({
    required this.onReady,
    required this.onTimedOut,
    required this.onCancelled,
    required this.onStopped,
    super.key,
  });

  final VoidCallback onReady;
  final VoidCallback onTimedOut;
  final VoidCallback onCancelled;
  final VoidCallback onStopped;

  @override
  ConsumerState<BlockingWaitPage> createState() => _BlockingWaitPageState();
}

class _BlockingWaitPageState extends ConsumerState<BlockingWaitPage> {
  int _handledNavigationRevision = 0;
  PlayRequestPhase? _handledTerminalPhase;
  bool _cancelling = false;

  @override
  Widget build(BuildContext context) {
    ref.listen<PlayRequestState>(playRequestControllerProvider, (_, next) {
      if (next.phase == PlayRequestPhase.ready &&
          next.navigationRevision > _handledNavigationRevision) {
        _handledNavigationRevision = next.navigationRevision;
        _schedule(widget.onReady);
      } else if (next.phase == PlayRequestPhase.timedOut &&
          _handledTerminalPhase != PlayRequestPhase.timedOut) {
        _handledTerminalPhase = PlayRequestPhase.timedOut;
        _schedule(widget.onTimedOut);
      } else if (next.phase == PlayRequestPhase.cancelled &&
          _handledTerminalPhase != PlayRequestPhase.cancelled) {
        _handledTerminalPhase = PlayRequestPhase.cancelled;
        _schedule(widget.onCancelled);
      } else if ((next.phase == PlayRequestPhase.failed ||
              next.phase == PlayRequestPhase.existing) &&
          _handledTerminalPhase != next.phase) {
        _handledTerminalPhase = next.phase;
        _schedule(widget.onStopped);
      }
    });
    final state = ref.watch(playRequestControllerProvider);
    final job = state.job;
    return PopScope(
      canPop: false,
      child: Scaffold(
        body: SafeArea(
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 560),
              child: Padding(
                padding: const EdgeInsets.all(32),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Icon(Icons.cloud_download_outlined, size: 56),
                    const SizedBox(height: 20),
                    Text(
                      '正在准备播放',
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.headlineSmall,
                    ),
                    const SizedBox(height: 10),
                    Text(_statusText(job?.status), textAlign: TextAlign.center),
                    const SizedBox(height: 24),
                    LinearProgressIndicator(
                      value:
                          job == null
                              ? null
                              : (job.remotePercent / 100).clamp(0.0, 1.0),
                    ),
                    const SizedBox(height: 12),
                    Text(
                      '剩余 ${state.remainingSeconds} 秒',
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      '固定容量：最多 2 个运行、10 个排队',
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      '关闭窗口不会取消任务，稍后完成会保留在缓存中。',
                      textAlign: TextAlign.center,
                    ),
                    if (state.errorCode != null) ...[
                      const SizedBox(height: 12),
                      Text(
                        '取消失败，请重试（${state.errorCode}）',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.error,
                        ),
                      ),
                    ],
                    const SizedBox(height: 28),
                    Align(
                      alignment: Alignment.center,
                      child: OutlinedButton.icon(
                        key: const ValueKey('wait-cancel'),
                        onPressed: _cancelling ? null : _confirmCancel,
                        icon: const Icon(Icons.close),
                        label: const Text('取消任务'),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _confirmCancel() async {
    final confirmed = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder:
          (context) => AlertDialog(
            title: const Text('取消缓存任务？'),
            content: const Text('取消后需要重新选择来源才能再次准备播放。'),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(context).pop(false),
                child: const Text('返回等待'),
              ),
              FilledButton(
                onPressed: () => Navigator.of(context).pop(true),
                child: const Text('确认取消'),
              ),
            ],
          ),
    );
    if (confirmed != true || !mounted) return;
    setState(() => _cancelling = true);
    await ref
        .read(playRequestControllerProvider.notifier)
        .cancel(confirmed: true);
    if (mounted) setState(() => _cancelling = false);
  }

  void _schedule(VoidCallback callback) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) callback();
    });
  }
}

String _statusText(String? status) => switch (status) {
  'submitting' => '正在提交离线任务',
  'offlining' => '115 正在离线下载',
  'submit_uncertain' => '正在确认任务状态',
  'resolving' => '正在解析媒体文件',
  'awaiting_selection' => '需要在缓存页选择媒体文件',
  _ => '正在等待缓存状态更新',
};

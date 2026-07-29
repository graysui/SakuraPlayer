import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/core/api/api_models.dart';
import 'package:sakuraplayer_windows/core/events/snapshot_controller.dart';

class CacheBadge extends ConsumerWidget {
  const CacheBadge({required this.onPressed, this.queues, super.key});

  final VoidCallback onPressed;
  final QueueSnapshot? queues;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final value = queues ?? ref.watch(snapshotStateProvider).queues;
    return SizedBox(
      width: 136,
      height: 44,
      child: Semantics(
        label:
            '缓存状态：排队 ${value.cacheQueued}，运行 ${value.cacheRunning}，就绪 ${value.cacheReady}',
        button: true,
        child: Tooltip(
          message: '缓存状态',
          child: Material(
            color: Theme.of(context).colorScheme.surfaceContainerHighest,
            borderRadius: BorderRadius.circular(6),
            child: InkWell(
              onTap: onPressed,
              borderRadius: BorderRadius.circular(6),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Icon(Icons.storage_outlined, size: 20),
                  const SizedBox(width: 6),
                  _Count(
                    key: const ValueKey('cache-queued-count'),
                    icon: Icons.schedule,
                    value: value.cacheQueued,
                  ),
                  _Count(
                    key: const ValueKey('cache-running-count'),
                    icon: Icons.sync,
                    value: value.cacheRunning,
                  ),
                  _Count(
                    key: const ValueKey('cache-ready-count'),
                    icon: Icons.check_circle_outline,
                    value: value.cacheReady,
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _Count extends StatelessWidget {
  const _Count({required this.icon, required this.value, super.key});

  final IconData icon;
  final int value;

  @override
  Widget build(BuildContext context) {
    final text = value > 99 ? '99+' : '$value';
    return SizedBox(
      width: 31,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(icon, size: 14),
          Text(
            text,
            maxLines: 1,
            style: Theme.of(context).textTheme.labelSmall,
          ),
        ],
      ),
    );
  }
}

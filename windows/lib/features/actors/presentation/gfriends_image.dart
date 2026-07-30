import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/core/images/gfriends_cache.dart';

class GfriendsImage extends ConsumerStatefulWidget {
  const GfriendsImage({
    required this.url,
    required this.fit,
    required this.missingLabel,
    this.missingIcon = Icons.person_outline,
    super.key,
  });

  final String? url;
  final BoxFit fit;
  final String missingLabel;
  final IconData missingIcon;

  @override
  ConsumerState<GfriendsImage> createState() => _GfriendsImageState();
}

class _GfriendsImageState extends ConsumerState<GfriendsImage> {
  GfriendsLoadHandle? _handle;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(GfriendsImage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.url != widget.url) _load();
  }

  void _load() {
    _handle?.cancel();
    final url = widget.url;
    _handle = url == null ? null : ref.read(gfriendsCacheProvider).load(url);
  }

  void _retry() {
    setState(_load);
  }

  @override
  void dispose() {
    _handle?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final handle = _handle;
    if (widget.url == null || handle == null) {
      return _ImagePlaceholder(
        icon: widget.missingIcon,
        label: widget.missingLabel,
      );
    }
    return FutureBuilder<Uint8List>(
      future: handle.bytes,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const ColoredBox(
            color: Colors.transparent,
            child: Center(
              child: SizedBox.square(
                dimension: 28,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
            ),
          );
        }
        final bytes = snapshot.data;
        if (snapshot.hasError || bytes == null) {
          return _ImagePlaceholder(
            icon: Icons.broken_image_outlined,
            label: '图片加载失败',
            onRetry: _retry,
          );
        }
        return Image.memory(
          bytes,
          fit: widget.fit,
          gaplessPlayback: true,
          errorBuilder:
              (context, error, stackTrace) => _ImagePlaceholder(
                icon: Icons.broken_image_outlined,
                label: '图片加载失败',
                onRetry: _retry,
              ),
        );
      },
    );
  }
}

class _ImagePlaceholder extends StatelessWidget {
  const _ImagePlaceholder({
    required this.icon,
    required this.label,
    this.onRetry,
  });

  final IconData icon;
  final String label;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) => ColoredBox(
    color: Theme.of(context).colorScheme.surfaceContainerHigh,
    child: Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            icon,
            size: 36,
            color: Theme.of(context).colorScheme.onSurfaceVariant,
          ),
          const SizedBox(height: 8),
          Text(label, style: Theme.of(context).textTheme.labelMedium),
          if (onRetry != null) ...[
            const SizedBox(height: 4),
            IconButton(
              onPressed: onRetry,
              tooltip: '重试图片',
              icon: const Icon(Icons.refresh, size: 20),
            ),
          ],
        ],
      ),
    ),
  );
}

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/features/search/data/search_api.dart';
import 'package:sakuraplayer_windows/features/search/presentation/search_controller.dart';

class SearchOverlay extends ConsumerWidget {
  const SearchOverlay({this.compact = false, super.key});

  final bool compact;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return SizedBox(
      height: 44,
      child: Tooltip(
        message: '全局搜索',
        child: Material(
          color: Theme.of(context).colorScheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(6),
          child: InkWell(
            onTap: () {
              ref.read(searchControllerProvider.notifier).clear();
              showDialog<void>(
                context: context,
                builder: (context) => const _SearchDialog(),
              );
            },
            borderRadius: BorderRadius.circular(6),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 14),
              child: Row(
                children: [
                  const Icon(Icons.search, size: 20),
                  if (!compact) ...[
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        '搜索番号、影片或女优',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.bodyMedium,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _SearchDialog extends ConsumerStatefulWidget {
  const _SearchDialog();

  @override
  ConsumerState<_SearchDialog> createState() => _SearchDialogState();
}

class _SearchDialogState extends ConsumerState<_SearchDialog> {
  final TextEditingController _text = TextEditingController();

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(searchControllerProvider);
    return Dialog(
      insetPadding: const EdgeInsets.all(24),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 680, maxHeight: 620),
        child: SizedBox(
          width: 680,
          height: 560,
          child: Column(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 20, 12, 12),
                child: Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _text,
                        autofocus: true,
                        maxLength: 200,
                        onChanged:
                            ref
                                .read(searchControllerProvider.notifier)
                                .updateQuery,
                        decoration: const InputDecoration(
                          hintText: '番号、影片标题、女优姓名或别名',
                          prefixIcon: Icon(Icons.search),
                          counterText: '',
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    IconButton(
                      onPressed: () => Navigator.of(context).pop(),
                      tooltip: '关闭',
                      icon: const Icon(Icons.close),
                    ),
                  ],
                ),
              ),
              const Divider(height: 1),
              Expanded(child: _SearchResults(state: state)),
            ],
          ),
        ),
      ),
    );
  }
}

class _SearchResults extends StatelessWidget {
  const _SearchResults({required this.state});

  final SearchState state;

  @override
  Widget build(BuildContext context) {
    if (state.status == SearchStatus.idle) {
      return const SizedBox.shrink();
    }
    if (state.status == SearchStatus.loading && state.result == null) {
      return const Center(
        child: SizedBox.square(
          dimension: 28,
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
      );
    }
    if (state.status == SearchStatus.failed && state.result == null) {
      return const Center(child: Text('搜索失败'));
    }
    final result = state.result!;
    if (result.movies.isEmpty &&
        result.actors.isEmpty &&
        result.pendingMetadata.isEmpty) {
      return const Center(child: Text('未找到结果'));
    }
    return Stack(
      children: [
        ListView(
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 20),
          children: [
            if (result.movies.isNotEmpty) ...[
              const _GroupHeading('影片'),
              for (final movie in result.movies)
                ListTile(
                  leading: const Icon(Icons.movie_outlined),
                  title: Text(movie.title, maxLines: 1),
                  subtitle: Text(movie.number, maxLines: 1),
                ),
            ],
            if (result.actors.isNotEmpty) ...[
              const _GroupHeading('女优'),
              for (final actor in result.actors)
                ListTile(
                  leading: const Icon(Icons.person_outline),
                  title: Text(actor.displayName, maxLines: 1),
                  subtitle:
                      actor.aliases.isEmpty
                          ? null
                          : Text(
                            actor.aliases.join(' · '),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                ),
            ],
            if (result.pendingMetadata.isNotEmpty) ...[
              const _GroupHeading('元数据补全'),
              for (final pending in result.pendingMetadata)
                _PendingMetadataTile(pending: pending),
            ],
          ],
        ),
        if (state.isRefreshing)
          const Positioned(
            left: 0,
            right: 0,
            top: 0,
            child: LinearProgressIndicator(minHeight: 2),
          ),
      ],
    );
  }
}

class _GroupHeading extends StatelessWidget {
  const _GroupHeading(this.label);

  final String label;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 4),
      child: Text(label, style: Theme.of(context).textTheme.titleSmall),
    );
  }
}

class _PendingMetadataTile extends StatelessWidget {
  const _PendingMetadataTile({required this.pending});

  final PendingMetadataDto pending;

  @override
  Widget build(BuildContext context) {
    final (Widget leading, String label) = switch (pending.state) {
      PendingMetadataState.queued => (
        const SizedBox.square(
          dimension: 20,
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
        '等待补全',
      ),
      PendingMetadataState.running => (
        const SizedBox.square(
          dimension: 20,
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
        '正在补全',
      ),
      PendingMetadataState.failed => (
        Icon(Icons.error_outline, color: Theme.of(context).colorScheme.error),
        '补全失败',
      ),
    };
    return ListTile(
      leading: leading,
      title: Text(pending.number, maxLines: 1),
      subtitle: Text(label),
    );
  }
}

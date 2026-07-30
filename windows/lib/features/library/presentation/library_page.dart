import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/features/library/data/movies_api.dart';
import 'package:sakuraplayer_windows/features/library/presentation/library_controller.dart';
import 'package:sakuraplayer_windows/features/library/presentation/library_filters.dart';
import 'package:sakuraplayer_windows/features/library/presentation/movie_card.dart';

class LibraryPage extends ConsumerStatefulWidget {
  const LibraryPage({this.onOpenMovie, super.key});

  final ValueChanged<String>? onOpenMovie;

  @override
  ConsumerState<LibraryPage> createState() => _LibraryPageState();
}

class _LibraryPageState extends ConsumerState<LibraryPage> {
  final ScrollController _scrollController = ScrollController();

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        unawaited(ref.read(libraryControllerProvider.notifier).loadInitial());
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
      unawaited(ref.read(libraryControllerProvider.notifier).loadMore());
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(libraryControllerProvider);
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
                20,
              ),
              sliver: SliverToBoxAdapter(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '媒体库',
                      style: Theme.of(context).textTheme.headlineSmall,
                    ),
                    const SizedBox(height: 16),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: LibraryFilters(
                        filters: state.filters,
                        onChanged: _applyFilters,
                      ),
                    ),
                    if (state.validationMessage != null) ...[
                      const SizedBox(height: 8),
                      Text(
                        state.validationMessage!,
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.error,
                        ),
                      ),
                    ],
                  ],
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
    LibraryState state,
    double horizontalPadding,
    int columns,
  ) {
    if (state.status == LibraryStatus.idle ||
        state.status == LibraryStatus.loading) {
      return const [
        SliverFillRemaining(
          hasScrollBody: false,
          child: Center(child: CircularProgressIndicator()),
        ),
      ];
    }
    if (state.status == LibraryStatus.failed) {
      return [
        SliverFillRemaining(
          hasScrollBody: false,
          child: _InitialError(
            onRetry:
                () => unawaited(
                  ref.read(libraryControllerProvider.notifier).retryInitial(),
                ),
          ),
        ),
      ];
    }
    if (state.status == LibraryStatus.invalid) {
      return const [
        SliverFillRemaining(
          hasScrollBody: false,
          child: Center(child: Text('请修正筛选条件')),
        ),
      ];
    }
    if (state.items.isEmpty) {
      return const [
        SliverFillRemaining(
          hasScrollBody: false,
          child: Center(child: Text('没有符合筛选条件的影片')),
        ),
      ];
    }
    final gateway = ref.read(moviesGatewayProvider);
    return [
      SliverPadding(
        padding: EdgeInsets.fromLTRB(
          horizontalPadding,
          0,
          horizontalPadding,
          20,
        ),
        sliver: SliverGrid(
          key: const ValueKey('library-grid'),
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: columns,
            mainAxisExtent: 408,
            crossAxisSpacing: 16,
            mainAxisSpacing: 16,
          ),
          delegate: SliverChildBuilderDelegate((context, index) {
            final movie = state.items[index];
            return MovieCard(
              key: ValueKey(movie.id),
              movie: movie,
              coverLoader: gateway.loadCover,
              onOpen:
                  widget.onOpenMovie == null
                      ? null
                      : () => widget.onOpenMovie!(movie.id),
            );
          }, childCount: state.items.length),
        ),
      ),
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
                                    .read(libraryControllerProvider.notifier)
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
    ];
  }

  void _applyFilters(MovieFilters filters) {
    if (_scrollController.hasClients) _scrollController.jumpTo(0);
    unawaited(
      ref.read(libraryControllerProvider.notifier).applyFilters(filters),
    );
  }
}

class _InitialError extends StatelessWidget {
  const _InitialError({required this.onRetry});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.cloud_off_outlined, size: 40),
          const SizedBox(height: 12),
          const Text('媒体库加载失败'),
          const SizedBox(height: 12),
          FilledButton(onPressed: onRetry, child: const Text('重试')),
        ],
      ),
    );
  }
}

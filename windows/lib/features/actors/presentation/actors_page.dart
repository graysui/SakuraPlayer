import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/features/actors/data/actors_api.dart';
import 'package:sakuraplayer_windows/features/actors/presentation/actors_controller.dart';
import 'package:sakuraplayer_windows/features/actors/presentation/gfriends_image.dart';

class ActorsPage extends ConsumerStatefulWidget {
  const ActorsPage({required this.onOpenActor, super.key});

  final ValueChanged<String> onOpenActor;

  @override
  ConsumerState<ActorsPage> createState() => _ActorsPageState();
}

class _ActorsPageState extends ConsumerState<ActorsPage> {
  final ScrollController _scrollController = ScrollController();
  final TextEditingController _searchController = TextEditingController();
  Timer? _searchTimer;

  @override
  void initState() {
    super.initState();
    _searchController.text =
        ref.read(actorsControllerProvider).scope.normalizedQuery ?? '';
    _scrollController.addListener(_onScroll);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        unawaited(ref.read(actorsControllerProvider.notifier).ensureLoaded());
      }
    });
  }

  @override
  void dispose() {
    _searchTimer?.cancel();
    _searchController.dispose();
    _scrollController
      ..removeListener(_onScroll)
      ..dispose();
    super.dispose();
  }

  void _onScroll() {
    if (!_scrollController.hasClients) return;
    final position = _scrollController.position;
    if (position.maxScrollExtent - position.pixels <= 480) {
      unawaited(ref.read(actorsControllerProvider.notifier).loadMore());
    }
  }

  void _scheduleSearch(String value) {
    _searchTimer?.cancel();
    _searchTimer = Timer(const Duration(milliseconds: 300), _submitSearch);
  }

  void _submitSearch() {
    _searchTimer?.cancel();
    final state = ref.read(actorsControllerProvider);
    unawaited(
      _applyScope(
        ActorListScope(
          query: _searchController.text,
          favorite: state.scope.favorite,
        ),
      ),
    );
  }

  Future<void> _applyScope(ActorListScope scope) async {
    await ref.read(actorsControllerProvider.notifier).applyScope(scope);
    if (mounted && _scrollController.hasClients) {
      _scrollController.jumpTo(0);
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(actorsControllerProvider);
    return LayoutBuilder(
      builder: (context, constraints) {
        final horizontalPadding = constraints.maxWidth < 900 ? 16.0 : 24.0;
        final gridWidth = constraints.maxWidth - horizontalPadding * 2;
        final columns = ((gridWidth + 16) / (200 + 16)).floor().clamp(1, 100);
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
              sliver: SliverToBoxAdapter(child: _header(context, state)),
            ),
            ..._content(context, state, horizontalPadding, columns),
          ],
        );
      },
    );
  }

  Widget _header(BuildContext context, ActorsState state) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Row(
        children: [
          Expanded(
            child: Text('女优', style: Theme.of(context).textTheme.headlineSmall),
          ),
          IconButton(
            onPressed:
                state.isRefreshing
                    ? null
                    : () => unawaited(
                      ref.read(actorsControllerProvider.notifier).refresh(),
                    ),
            tooltip: '刷新女优列表',
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      const SizedBox(height: 14),
      Wrap(
        spacing: 12,
        runSpacing: 12,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          SizedBox(
            width: 420,
            child: TextField(
              key: const ValueKey('actors-search-field'),
              controller: _searchController,
              maxLength: 200,
              onChanged: _scheduleSearch,
              onSubmitted: (_) => _submitSearch(),
              decoration: const InputDecoration(
                hintText: '搜索姓名或权威别名',
                prefixIcon: Icon(Icons.search),
                counterText: '',
              ),
            ),
          ),
          SegmentedButton<bool>(
            segments: const <ButtonSegment<bool>>[
              ButtonSegment<bool>(
                value: false,
                label: Text('全部'),
                icon: Icon(Icons.people_outline),
              ),
              ButtonSegment<bool>(
                value: true,
                label: Text('收藏'),
                icon: Icon(Icons.favorite_outline),
              ),
            ],
            selected: <bool>{state.scope.favorite},
            onSelectionChanged:
                (selection) => unawaited(
                  _applyScope(
                    ActorListScope(
                      query: _searchController.text,
                      favorite: selection.single,
                    ),
                  ),
                ),
          ),
        ],
      ),
      if (state.isRefreshing) ...[
        const SizedBox(height: 12),
        const LinearProgressIndicator(minHeight: 2),
      ] else if (state.refreshErrorCode != null) ...[
        const SizedBox(height: 12),
        _InlineRetry(
          label: '刷新失败，已保留当前列表',
          onRetry:
              () => unawaited(
                ref.read(actorsControllerProvider.notifier).refresh(),
              ),
        ),
      ],
    ],
  );

  List<Widget> _content(
    BuildContext context,
    ActorsState state,
    double horizontalPadding,
    int columns,
  ) {
    if (state.status == ActorsStatus.idle ||
        state.status == ActorsStatus.loading) {
      return const <Widget>[
        SliverFillRemaining(
          hasScrollBody: false,
          child: Center(child: CircularProgressIndicator()),
        ),
      ];
    }
    if (state.status == ActorsStatus.failed) {
      return <Widget>[
        SliverFillRemaining(
          hasScrollBody: false,
          child: _PageMessage(
            icon: Icons.cloud_off_outlined,
            title: '女优列表加载失败',
            actionLabel: '重新加载',
            onAction:
                () => unawaited(
                  ref.read(actorsControllerProvider.notifier).retryInitial(),
                ),
          ),
        ),
      ];
    }
    if (state.items.isEmpty) {
      return const <Widget>[
        SliverFillRemaining(
          hasScrollBody: false,
          child: _PageMessage(
            icon: Icons.person_search_outlined,
            title: '没有找到女优',
          ),
        ),
      ];
    }
    return <Widget>[
      SliverPadding(
        padding: EdgeInsets.fromLTRB(
          horizontalPadding,
          0,
          horizontalPadding,
          20,
        ),
        sliver: SliverGrid(
          delegate: SliverChildBuilderDelegate((context, index) {
            final actor = state.items[index];
            return _ActorCard(
              key: ValueKey('actor-card-${actor.id}'),
              actor: actor,
              favoriteInFlight: state.favoriteInFlightIds.contains(actor.id),
              onOpen: () => widget.onOpenActor(actor.id),
              onFavorite:
                  () => unawaited(
                    ref
                        .read(actorsControllerProvider.notifier)
                        .setFavorite(actor.id, enabled: !actor.favorite),
                  ),
            );
          }, childCount: state.items.length),
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: columns,
            mainAxisExtent: 320,
            mainAxisSpacing: 16,
            crossAxisSpacing: 16,
          ),
        ),
      ),
      if (state.isAppending)
        const SliverToBoxAdapter(
          child: Padding(
            padding: EdgeInsets.all(20),
            child: Center(child: CircularProgressIndicator()),
          ),
        )
      else if (state.appendErrorCode != null)
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(24, 0, 24, 24),
            child: Center(
              child: _InlineRetry(
                label: '后续内容加载失败',
                onRetry:
                    () => unawaited(
                      ref.read(actorsControllerProvider.notifier).retryAppend(),
                    ),
              ),
            ),
          ),
        ),
    ];
  }
}

class _ActorCard extends StatelessWidget {
  const _ActorCard({
    required this.actor,
    required this.favoriteInFlight,
    required this.onOpen,
    required this.onFavorite,
    super.key,
  });

  final ActorSummaryDto actor;
  final bool favoriteInFlight;
  final VoidCallback onOpen;
  final VoidCallback onFavorite;

  @override
  Widget build(BuildContext context) => Card(
    margin: EdgeInsets.zero,
    clipBehavior: Clip.antiAlias,
    child: InkWell(
      onTap: onOpen,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SizedBox(
            height: 220,
            child: Stack(
              fit: StackFit.expand,
              children: [
                GfriendsImage(
                  url: actor.profileUrl,
                  fit: BoxFit.cover,
                  missingLabel: '暂无头像',
                ),
                Positioned(
                  right: 6,
                  top: 6,
                  child: IconButton.filledTonal(
                    onPressed: favoriteInFlight ? null : onFavorite,
                    tooltip: actor.favorite ? '取消收藏' : '收藏女优',
                    icon:
                        favoriteInFlight
                            ? const SizedBox.square(
                              dimension: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                            : Icon(
                              actor.favorite
                                  ? Icons.favorite
                                  : Icons.favorite_outline,
                              size: 20,
                            ),
                  ),
                ),
              ],
            ),
          ),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    actor.displayName,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 4),
                  if (_secondaryNames(actor).isNotEmpty) ...[
                    Text(
                      _secondaryNames(actor).join(' · '),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                    const SizedBox(height: 4),
                  ],
                  Expanded(
                    child: Text(
                      actor.aliases.isEmpty
                          ? '暂无别名'
                          : actor.aliases.join(' · '),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    ),
  );
}

List<String> _secondaryNames(ActorSummaryDto actor) {
  final result = <String>[];
  for (final value in <String?>[actor.nameZh, actor.nameJa]) {
    if (value != null && value.isNotEmpty && value != actor.displayName) {
      result.add(value);
    }
  }
  return result.toSet().toList(growable: false);
}

class _InlineRetry extends StatelessWidget {
  const _InlineRetry({required this.label, required this.onRetry});

  final String label;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      Flexible(child: Text(label)),
      const SizedBox(width: 8),
      TextButton.icon(
        onPressed: onRetry,
        icon: const Icon(Icons.refresh, size: 18),
        label: const Text('重试'),
      ),
    ],
  );
}

class _PageMessage extends StatelessWidget {
  const _PageMessage({
    required this.icon,
    required this.title,
    this.actionLabel,
    this.onAction,
  });

  final IconData icon;
  final String title;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) => Center(
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 48),
        const SizedBox(height: 12),
        Text(title, style: Theme.of(context).textTheme.titleMedium),
        if (actionLabel != null && onAction != null) ...[
          const SizedBox(height: 12),
          FilledButton.icon(
            onPressed: onAction,
            icon: const Icon(Icons.refresh),
            label: Text(actionLabel!),
          ),
        ],
      ],
    ),
  );
}

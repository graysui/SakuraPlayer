import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:sakuraplayer_windows/features/library/data/movies_api.dart';

class LibraryFilters extends StatefulWidget {
  const LibraryFilters({
    required this.filters,
    required this.onChanged,
    super.key,
  });

  final MovieFilters filters;
  final ValueChanged<MovieFilters> onChanged;

  @override
  State<LibraryFilters> createState() => _LibraryFiltersState();
}

class _LibraryFiltersState extends State<LibraryFilters> {
  late final TextEditingController _minimumController;
  late final TextEditingController _maximumController;

  @override
  void initState() {
    super.initState();
    _minimumController = TextEditingController(
      text: widget.filters.minResourceSizeMb?.toString() ?? '',
    );
    _maximumController = TextEditingController(
      text: widget.filters.maxResourceSizeMb?.toString() ?? '',
    );
  }

  @override
  void didUpdateWidget(LibraryFilters oldWidget) {
    super.didUpdateWidget(oldWidget);
    _syncController(
      _minimumController,
      widget.filters.minResourceSizeMb?.toString() ?? '',
    );
    _syncController(
      _maximumController,
      widget.filters.maxResourceSizeMb?.toString() ?? '',
    );
  }

  @override
  void dispose() {
    _minimumController.dispose();
    _maximumController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 1180),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _FilterRow(
            label: '分类',
            children: [
              for (final category in avdbCategories)
                FilterChip(
                  label: Text(category),
                  selected: widget.filters.categories.contains(category),
                  onSelected: (_) => _toggleCategory(category),
                ),
            ],
          ),
          const SizedBox(height: 8),
          _FilterRow(
            label: '标签',
            children: [
              for (final entry in _labelNames.entries)
                FilterChip(
                  label: Text(entry.value),
                  selected: widget.filters.labels.contains(entry.key),
                  onSelected: (_) => _toggleLabel(entry.key),
                ),
            ],
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 12,
            runSpacing: 12,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              SizedBox(
                width: 160,
                child: DropdownButtonFormField<String>(
                  value: widget.filters.sourceWebsite?.name ?? 'all',
                  decoration: const InputDecoration(
                    labelText: '来源',
                    isDense: true,
                  ),
                  items: const [
                    DropdownMenuItem(value: 'all', child: Text('全部来源')),
                    DropdownMenuItem(value: 'sehuatang', child: Text('色花堂')),
                    DropdownMenuItem(value: 'x1080x', child: Text('X1080X')),
                  ],
                  onChanged: (value) {
                    final website = switch (value) {
                      'sehuatang' => MovieSourceWebsite.sehuatang,
                      'x1080x' => MovieSourceWebsite.x1080x,
                      _ => null,
                    };
                    widget.onChanged(
                      widget.filters.copyWith(sourceWebsite: website),
                    );
                  },
                ),
              ),
              SizedBox(
                width: 160,
                child: DropdownButtonFormField<String>(
                  value: switch (widget.filters.playable) {
                    true => 'ready',
                    false => 'not_ready',
                    null => 'all',
                  },
                  decoration: const InputDecoration(
                    labelText: '可播放状态',
                    isDense: true,
                  ),
                  items: const [
                    DropdownMenuItem(value: 'all', child: Text('全部状态')),
                    DropdownMenuItem(value: 'ready', child: Text('可播放')),
                    DropdownMenuItem(value: 'not_ready', child: Text('未就绪')),
                  ],
                  onChanged: (value) {
                    final playable = switch (value) {
                      'ready' => true,
                      'not_ready' => false,
                      _ => null,
                    };
                    widget.onChanged(
                      widget.filters.copyWith(playable: playable),
                    );
                  },
                ),
              ),
              SizedBox(
                width: 132,
                child: TextField(
                  key: const ValueKey('minimum-resource-size'),
                  controller: _minimumController,
                  keyboardType: TextInputType.number,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                  textInputAction: TextInputAction.done,
                  decoration: const InputDecoration(
                    labelText: '最小 MiB',
                    isDense: true,
                  ),
                  onSubmitted:
                      (value) => widget.onChanged(
                        widget.filters.copyWith(
                          minResourceSizeMb: _parseSize(value),
                        ),
                      ),
                ),
              ),
              SizedBox(
                width: 132,
                child: TextField(
                  key: const ValueKey('maximum-resource-size'),
                  controller: _maximumController,
                  keyboardType: TextInputType.number,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                  textInputAction: TextInputAction.done,
                  decoration: const InputDecoration(
                    labelText: '最大 MiB',
                    isDense: true,
                  ),
                  onSubmitted:
                      (value) => widget.onChanged(
                        widget.filters.copyWith(
                          maxResourceSizeMb: _parseSize(value),
                        ),
                      ),
                ),
              ),
              SizedBox(
                width: 190,
                child: DropdownButtonFormField<MovieSort>(
                  value: widget.filters.sort,
                  decoration: const InputDecoration(
                    labelText: '排序',
                    isDense: true,
                  ),
                  items: const [
                    DropdownMenuItem(
                      value: MovieSort.publishDateDesc,
                      child: Text('发布日期：新到旧'),
                    ),
                    DropdownMenuItem(
                      value: MovieSort.publishDateAsc,
                      child: Text('发布日期：旧到新'),
                    ),
                    DropdownMenuItem(
                      value: MovieSort.numberAsc,
                      child: Text('番号'),
                    ),
                  ],
                  onChanged: (value) {
                    if (value != null) {
                      widget.onChanged(widget.filters.copyWith(sort: value));
                    }
                  },
                ),
              ),
              SizedBox(
                width: 130,
                child: CheckboxListTile(
                  value: widget.filters.favorite,
                  onChanged:
                      (value) => widget.onChanged(
                        widget.filters.copyWith(favorite: value ?? false),
                      ),
                  title: const Text('仅收藏'),
                  controlAffinity: ListTileControlAffinity.leading,
                  contentPadding: EdgeInsets.zero,
                  dense: true,
                ),
              ),
              IconButton(
                onPressed: () => widget.onChanged(const MovieFilters()),
                tooltip: '重置筛选',
                icon: const Icon(Icons.filter_alt_off_outlined),
              ),
            ],
          ),
        ],
      ),
    );
  }

  void _toggleCategory(String value) {
    final categories = <String>{...widget.filters.categories};
    categories.contains(value)
        ? categories.remove(value)
        : categories.add(value);
    widget.onChanged(widget.filters.copyWith(categories: categories));
  }

  void _toggleLabel(String value) {
    final labels = <String>{...widget.filters.labels};
    labels.contains(value) ? labels.remove(value) : labels.add(value);
    widget.onChanged(widget.filters.copyWith(labels: labels));
  }

  static int? _parseSize(String value) {
    final normalized = value.trim();
    return normalized.isEmpty ? null : int.tryParse(normalized);
  }

  static void _syncController(TextEditingController controller, String value) {
    if (controller.text != value) controller.text = value;
  }
}

class _FilterRow extends StatelessWidget {
  const _FilterRow({required this.label, required this.children});

  final String label;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 48,
          child: Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(label, style: Theme.of(context).textTheme.labelLarge),
          ),
        ),
        Expanded(child: Wrap(spacing: 8, runSpacing: 8, children: children)),
      ],
    );
  }
}

const _labelNames = <String, String>{
  'subtitle': '字幕',
  'cracked': '破解',
  '4k': '4K',
  'censored': '有码',
};

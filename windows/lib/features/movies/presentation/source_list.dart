import 'package:flutter/material.dart';
import 'package:sakuraplayer_windows/features/movies/data/movie_detail_api.dart';

class SourceList extends StatelessWidget {
  const SourceList({
    required this.sources,
    required this.selectedSourceId,
    required this.onSelected,
    super.key,
  });

  final List<MovieSourceDto> sources;
  final String? selectedSourceId;
  final ValueChanged<String> onSelected;

  @override
  Widget build(BuildContext context) {
    if (sources.isEmpty) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 20),
        child: Text('暂无可用来源'),
      );
    }
    return ListView.separated(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      itemCount: sources.length,
      separatorBuilder: (context, index) => const Divider(height: 1),
      itemBuilder: (context, index) {
        final source = sources[index];
        return _SourceRow(
          key: ValueKey('source-row-$index'),
          source: source,
          selected: selectedSourceId == source.id,
          onSelected: onSelected,
        );
      },
    );
  }
}

class _SourceRow extends StatelessWidget {
  const _SourceRow({
    required this.source,
    required this.selected,
    required this.onSelected,
    super.key,
  });

  final MovieSourceDto source;
  final bool selected;
  final ValueChanged<String> onSelected;

  @override
  Widget build(BuildContext context) {
    final enabled = source.isSelectable;
    final colors = Theme.of(context).colorScheme;
    return ConstrainedBox(
      constraints: const BoxConstraints(minHeight: 88),
      child: Material(
        color: selected ? colors.secondaryContainer : Colors.transparent,
        child: InkWell(
          onTap: enabled ? () => onSelected(source.id) : null,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 10),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Radio<String>(
                  value: source.id,
                  groupValue: selected ? source.id : null,
                  onChanged: enabled ? (_) => onSelected(source.id) : null,
                ),
                const SizedBox(width: 4),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        source.title,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.titleSmall,
                      ),
                      const SizedBox(height: 5),
                      Wrap(
                        spacing: 8,
                        runSpacing: 4,
                        children: [
                          Text(_websiteLabel(source)),
                          Text(source.category),
                          if (source.publishDate != null)
                            Text(source.publishDate!),
                          for (final label in _orderedLabels(source.labels))
                            Text(_sourceLabelNames[label]!),
                        ],
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 12),
                SizedBox(
                  width: 144,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Text(
                        _availabilityLabel(source.availability),
                        style: TextStyle(
                          color:
                              enabled
                                  ? colors.primary
                                  : colors.onSurfaceVariant,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        _sizeLabel(source),
                        textAlign: TextAlign.end,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

String _websiteLabel(MovieSourceDto source) => switch (source.website.name) {
  'sehuatang' => '色花堂',
  'x1080x' => 'X1080X',
  _ => source.website.name,
};

Iterable<String> _orderedLabels(List<String> labels) =>
    _sourceLabelNames.keys.where(labels.contains);

String _availabilityLabel(MovieSourceAvailability availability) =>
    switch (availability) {
      MovieSourceAvailability.available => '可缓存',
      MovieSourceAvailability.queued => '排队中',
      MovieSourceAvailability.running => '处理中',
      MovieSourceAvailability.ready => '可播放',
      MovieSourceAvailability.failed => '上次失败',
      MovieSourceAvailability.rejected => '不可用',
    };

String _sizeLabel(MovieSourceDto source) {
  if (source.availability == MovieSourceAvailability.ready) {
    final bytes = source.videoFileSizeBytes;
    return bytes == null ? '视频文件大小未知' : '视频文件大小 ${_formatBytes(bytes)}';
  }
  final size = source.resourceSizeMb;
  return size == null ? '资源大小未知' : '资源大小 $size MiB';
}

String _formatBytes(int bytes) {
  const gib = 1024 * 1024 * 1024;
  const mib = 1024 * 1024;
  if (bytes >= gib) return '${_compact(bytes / gib)} GiB';
  if (bytes >= mib) return '${_compact(bytes / mib)} MiB';
  return '$bytes B';
}

String _compact(double value) =>
    value == value.roundToDouble()
        ? value.toStringAsFixed(0)
        : value.toStringAsFixed(1);

const _sourceLabelNames = <String, String>{
  'subtitle': '字幕',
  'cracked': '破解',
  '4k': '4K',
  'censored': '有码',
};

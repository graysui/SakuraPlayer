import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sakuraplayer_windows/core/events/snapshot_controller.dart';
import 'package:sakuraplayer_windows/features/playback/data/playback_api.dart';
import 'package:sakuraplayer_windows/features/playback/data/subtitle_cache.dart';
import 'package:sakuraplayer_windows/features/playback/presentation/playback_engine.dart';
import 'package:sakuraplayer_windows/features/playback/presentation/player_controller.dart';
import 'package:sakuraplayer_windows/features/playback/presentation/progress_controller.dart';
import 'package:sakuraplayer_windows/features/playback/presentation/track_controller.dart';
import 'package:sakuraplayer_windows/theme/player_theme.dart';

class PlayerPage extends ConsumerStatefulWidget {
  const PlayerPage({
    super.key,
    required this.cacheJobId,
    required this.mediaId,
    this.onBack,
    this.controller,
  });

  final String cacheJobId;
  final String mediaId;
  final VoidCallback? onBack;
  final PlayerController? controller;

  @override
  ConsumerState<PlayerPage> createState() => _PlayerPageState();
}

class _PlayerPageState extends ConsumerState<PlayerPage> {
  late final PlayerController _controller;
  late final bool _ownsController;

  @override
  void initState() {
    super.initState();
    _ownsController = widget.controller == null;
    if (widget.controller case final injected?) {
      _controller = injected;
    } else {
      final engine = ref.read(playbackEngineFactoryProvider)();
      final movieId =
          ref.read(snapshotStateProvider).cacheJobs[widget.cacheJobId]?.movieId;
      _controller = PlayerController(
        gateway: ref.read(playbackGatewayProvider),
        engine: engine,
        tracks: TrackController(
          port: engine,
          subtitles: ref.read(subtitleRepositoryProvider),
        ),
        progress: ProgressController(
          gateway: ref.read(playbackProgressGatewayProvider),
          movieId: movieId,
          onProgress:
              movieId == null
                  ? null
                  : (progress) => ref
                      .read(livePlaybackProgressProvider.notifier)
                      .update(movieId, progress),
        ),
      );
    }
    _controller.addListener(_changed);
    unawaited(
      _controller.initialize(
        cacheJobId: widget.cacheJobId,
        mediaId: widget.mediaId,
      ),
    );
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    _controller.removeListener(_changed);
    if (_ownsController) unawaited(_controller.close());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Theme(
      data: SakuraPlayerTheme.dark,
      child: Shortcuts(
        shortcuts: const <ShortcutActivator, Intent>{
          SingleActivator(LogicalKeyboardKey.space): _TogglePlayIntent(),
          SingleActivator(LogicalKeyboardKey.arrowLeft): _SeekIntent(-10),
          SingleActivator(LogicalKeyboardKey.arrowRight): _SeekIntent(10),
        },
        child: Actions(
          actions: <Type, Action<Intent>>{
            _TogglePlayIntent: CallbackAction<_TogglePlayIntent>(
              onInvoke: (_) => unawaited(_controller.togglePlayPause()),
            ),
            _SeekIntent: CallbackAction<_SeekIntent>(
              onInvoke:
                  (intent) => unawaited(
                    _controller.seekBy(Duration(seconds: intent.seconds)),
                  ),
            ),
          },
          child: Focus(
            autofocus: true,
            child: Scaffold(
              backgroundColor: SakuraPlayerTheme.background,
              body: SafeArea(
                child: Column(
                  children: [
                    _PlayerHeader(
                      mode: _controller.mode,
                      busy: _controller.status == PlayerLoadStatus.loading,
                      onBack:
                          widget.onBack ?? () => Navigator.maybePop(context),
                      onModeSelected:
                          (mode) => unawaited(_controller.switchMode(mode)),
                    ),
                    Expanded(child: _buildBody()),
                    if (_controller.status == PlayerLoadStatus.ready)
                      _PlayerControls(controller: _controller),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildBody() => switch (_controller.status) {
    PlayerLoadStatus.idle || PlayerLoadStatus.loading => const Center(
      child: CircularProgressIndicator(),
    ),
    PlayerLoadStatus.failed => Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(_playerErrorLabel(_controller.errorCode)),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: () => unawaited(_controller.retry()),
            icon: const Icon(Icons.refresh),
            label: const Text('重试'),
          ),
        ],
      ),
    ),
    PlayerLoadStatus.ready => Stack(
      fit: StackFit.expand,
      children: [
        ColoredBox(
          key: const ValueKey('video-surface'),
          color: Colors.black,
          child: _controller.engine.buildVideoSurface(),
        ),
        if (_controller.isBuffering)
          const Center(child: CircularProgressIndicator()),
      ],
    ),
  };
}

class _PlayerHeader extends StatelessWidget {
  const _PlayerHeader({
    required this.mode,
    required this.busy,
    required this.onBack,
    required this.onModeSelected,
  });

  final PlaybackMode mode;
  final bool busy;
  final VoidCallback onBack;
  final ValueChanged<PlaybackMode> onModeSelected;

  @override
  Widget build(BuildContext context) => SizedBox(
    height: 52,
    child: Row(
      children: [
        IconButton(
          onPressed: onBack,
          tooltip: '返回缓存页',
          icon: const Icon(Icons.arrow_back),
        ),
        const Spacer(),
        PopupMenuButton<PlaybackMode>(
          enabled: !busy,
          tooltip: '播放模式',
          initialValue: mode,
          onSelected: onModeSelected,
          itemBuilder:
              (_) => const [
                PopupMenuItem(value: PlaybackMode.original, child: Text('原画')),
                PopupMenuItem(
                  value: PlaybackMode.compatibility,
                  child: Text('兼容播放'),
                ),
              ],
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.tune, size: 18),
                const SizedBox(width: 6),
                Text(mode == PlaybackMode.original ? '原画' : '兼容播放'),
              ],
            ),
          ),
        ),
        const SizedBox(width: 8),
      ],
    ),
  );
}

class _PlayerControls extends StatelessWidget {
  const _PlayerControls({required this.controller});

  final PlayerController controller;

  @override
  Widget build(BuildContext context) {
    final durationMs = controller.duration.inMilliseconds;
    final positionMs = controller.position.inMilliseconds.clamp(0, durationMs);
    return Container(
      key: const ValueKey('player-controls'),
      constraints: const BoxConstraints(minHeight: 72),
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 10),
      color: SakuraPlayerTheme.surface,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Slider(
            key: const ValueKey('player-progress'),
            min: 0,
            max: durationMs <= 0 ? 1 : durationMs.toDouble(),
            value: durationMs <= 0 ? 0 : positionMs.toDouble(),
            onChanged:
                durationMs <= 0
                    ? null
                    : (value) => unawaited(
                      controller.seek(Duration(milliseconds: value.round())),
                    ),
          ),
          Wrap(
            alignment: WrapAlignment.spaceBetween,
            crossAxisAlignment: WrapCrossAlignment.center,
            spacing: 4,
            runSpacing: 4,
            children: [
              IconButton(
                onPressed: () => unawaited(controller.togglePlayPause()),
                tooltip: controller.isPlaying ? '暂停' : '播放',
                icon: Icon(
                  controller.isPlaying ? Icons.pause : Icons.play_arrow,
                ),
              ),
              SizedBox(
                width: 118,
                child: Text(
                  '${_durationLabel(controller.position)} / ${_durationLabel(controller.duration)}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              if (controller.tracks case final tracks?) ...[
                PopupMenuButton<String>(
                  enabled: tracks.audioTracks.isNotEmpty,
                  tooltip: '音轨',
                  initialValue: tracks.selectedAudioId,
                  onSelected: (id) => unawaited(tracks.selectAudio(id)),
                  itemBuilder:
                      (_) => [
                        for (final track in tracks.audioTracks)
                          PopupMenuItem(
                            value: track.id,
                            child: Text(track.label),
                          ),
                      ],
                  child: const SizedBox.square(
                    dimension: 40,
                    child: Icon(Icons.audiotrack),
                  ),
                ),
                PopupMenuButton<String>(
                  enabled: !tracks.loadingSubtitle,
                  tooltip: '字幕',
                  initialValue: tracks.selectedSubtitleKey,
                  onSelected: (key) => unawaited(tracks.selectSubtitle(key)),
                  itemBuilder:
                      (_) => [
                        for (final choice in tracks.subtitleChoices)
                          PopupMenuItem(
                            value: choice.key,
                            child: Text(choice.label),
                          ),
                      ],
                  child: SizedBox.square(
                    dimension: 40,
                    child:
                        tracks.loadingSubtitle
                            ? const Padding(
                              padding: EdgeInsets.all(10),
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                            : const Icon(Icons.subtitles),
                  ),
                ),
              ],
              PopupMenuButton<double>(
                tooltip: '播放速度',
                initialValue: controller.rate,
                onSelected: (rate) => unawaited(controller.setRate(rate)),
                itemBuilder:
                    (_) => const [
                      PopupMenuItem(value: 0.5, child: Text('0.5x')),
                      PopupMenuItem(value: 1, child: Text('1.0x')),
                      PopupMenuItem(value: 1.25, child: Text('1.25x')),
                      PopupMenuItem(value: 1.5, child: Text('1.5x')),
                      PopupMenuItem(value: 2, child: Text('2.0x')),
                    ],
                child: Padding(
                  padding: const EdgeInsets.all(8),
                  child: Text('${controller.rate}x'),
                ),
              ),
              IconButton(
                onPressed:
                    () => unawaited(controller.engine.toggleFullscreen()),
                tooltip: '全屏',
                icon: const Icon(Icons.fullscreen),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _TogglePlayIntent extends Intent {
  const _TogglePlayIntent();
}

class _SeekIntent extends Intent {
  const _SeekIntent(this.seconds);

  final int seconds;
}

String _durationLabel(Duration duration) {
  final hours = duration.inHours;
  final minutes = duration.inMinutes.remainder(60).toString().padLeft(2, '0');
  final seconds = duration.inSeconds.remainder(60).toString().padLeft(2, '0');
  return hours > 0 ? '$hours:$minutes:$seconds' : '$minutes:$seconds';
}

String _playerErrorLabel(String? code) => switch (code) {
  'cloud115_credentials_expired' => '115 凭据已失效，请重新扫码',
  'cloud115_file_not_found' => '媒体文件已不存在',
  'cloud115_rate_limited' => '请求过于频繁，请稍后重试',
  _ => '播放加载失败，请重试',
};

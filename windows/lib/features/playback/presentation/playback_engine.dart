import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:media_kit/media_kit.dart';
import 'package:media_kit_video/media_kit_video.dart';
import 'package:sakuraplayer_windows/features/playback/data/playback_api.dart';

abstract interface class PlaybackEngine {
  Stream<bool> get playingStream;
  Stream<bool> get bufferingStream;
  Stream<Duration> get positionStream;
  Stream<Duration> get durationStream;
  Stream<String> get errorStream;

  Widget buildVideoSurface();
  Future<void> open(PlaybackManifestDto manifest, String mediaId);
  Future<void> play();
  Future<void> pause();
  Future<void> seek(Duration target);
  Future<void> setRate(double rate);
  Future<void> toggleFullscreen();
  Future<void> dispose();
}

class MediaKitPlaybackEngine implements PlaybackEngine {
  MediaKitPlaybackEngine() : _player = Player() {
    _videoController = VideoController(_player);
  }

  final Player _player;
  late final VideoController _videoController;
  final GlobalKey<VideoState> _videoKey = GlobalKey<VideoState>();

  @override
  Stream<bool> get playingStream => _player.stream.playing;
  @override
  Stream<bool> get bufferingStream => _player.stream.buffering;
  @override
  Stream<Duration> get positionStream => _player.stream.position;
  @override
  Stream<Duration> get durationStream => _player.stream.duration;
  @override
  Stream<String> get errorStream => _player.stream.error;

  @override
  Widget buildVideoSurface() => Video(
    key: _videoKey,
    controller: _videoController,
    controls: (_) => const SizedBox.shrink(),
    fit: BoxFit.contain,
    fill: Colors.black,
  );

  @override
  Future<void> open(PlaybackManifestDto manifest, String mediaId) =>
      _player.open(buildMediaKitPlaylist(manifest, mediaId));

  @override
  Future<void> play() => _player.play();
  @override
  Future<void> pause() => _player.pause();
  @override
  Future<void> seek(Duration target) => _player.seek(target);
  @override
  Future<void> setRate(double rate) => _player.setRate(rate);

  @override
  Future<void> toggleFullscreen() async {
    final state = _videoKey.currentState;
    if (state == null) return;
    if (state.isFullscreen()) {
      await state.exitFullscreen();
    } else {
      await state.enterFullscreen();
    }
  }

  @override
  Future<void> dispose() => _player.dispose();
}

typedef PlaybackEngineFactory = PlaybackEngine Function();

final playbackEngineFactoryProvider = Provider<PlaybackEngineFactory>(
  (ref) => MediaKitPlaybackEngine.new,
);

Playlist buildMediaKitPlaylist(PlaybackManifestDto manifest, String mediaId) {
  final index = manifest.mediaQueue.indexWhere(
    (item) => item.media.id == mediaId,
  );
  if (index < 0) throw StateError('media is absent from manifest');
  return Playlist(
    manifest.mediaQueue
        .map(
          (item) => Media(
            item.streamUri.toString(),
            httpHeaders: const <String, String>{
              'User-Agent': windowsPlaybackUserAgent,
            },
          ),
        )
        .toList(growable: false),
    index: index,
  );
}

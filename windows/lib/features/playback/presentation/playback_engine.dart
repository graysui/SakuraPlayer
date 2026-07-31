import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:media_kit/media_kit.dart';
import 'package:media_kit_video/media_kit_video.dart';
import 'package:sakuraplayer_windows/features/playback/data/playback_api.dart';
import 'package:sakuraplayer_windows/features/playback/presentation/track_controller.dart';

abstract interface class PlaybackEngine implements TrackPlaybackPort {
  Stream<bool> get playingStream;
  Stream<bool> get completedStream;
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
  Stream<bool> get completedStream => _player.stream.completed;
  @override
  Stream<bool> get bufferingStream => _player.stream.buffering;
  @override
  Stream<Duration> get positionStream => _player.stream.position;
  @override
  Stream<Duration> get durationStream => _player.stream.duration;
  @override
  Stream<String> get errorStream => _player.stream.error;
  @override
  Stream<EmbeddedTrackCatalog> get trackCatalogStream =>
      _player.stream.tracks.map(
        (tracks) => EmbeddedTrackCatalog(
          audio: tracks.audio
              .where((track) => track.id != 'auto' && track.id != 'no')
              .map(
                (track) => EmbeddedTrackOption(
                  id: track.id,
                  title: track.title,
                  language: track.language,
                ),
              )
              .toList(growable: false),
          subtitles: tracks.subtitle
              .where((track) => track.id != 'auto' && track.id != 'no')
              .map(
                (track) => EmbeddedTrackOption(
                  id: track.id,
                  title: track.title,
                  language: track.language,
                ),
              )
              .toList(growable: false),
        ),
      );
  @override
  Stream<EmbeddedTrackSelection> get trackSelectionStream =>
      _player.stream.track.map(
        (track) => EmbeddedTrackSelection(
          audioId:
              track.audio.id == 'auto' || track.audio.id == 'no'
                  ? null
                  : track.audio.id,
          subtitleId:
              track.subtitle.id == 'auto' || track.subtitle.id == 'no'
                  ? null
                  : track.subtitle.id,
        ),
      );

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
  Future<void> selectAudioTrack(String id) =>
      _player.setAudioTrack(AudioTrack(id, null, null));

  @override
  Future<void> selectEmbeddedSubtitleTrack(String? id) =>
      _player.setSubtitleTrack(
        id == null ? SubtitleTrack.no() : SubtitleTrack(id, null, null),
      );

  @override
  Future<void> setExternalSubtitle(
    Uri uri, {
    required String title,
    required String? language,
  }) => _player.setSubtitleTrack(
    SubtitleTrack.uri(uri.toString(), title: title, language: language),
  );

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

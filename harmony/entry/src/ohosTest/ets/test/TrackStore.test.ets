/**
 * TASK-311 TrackStore 测试：内嵌/外置/无字幕、多音轨、四格式、字幕失败继续视频。
 */

import { describe, it, expect } from '@ohos/hypium';
import AbilityDelegatorRegistry from '@ohos.app.ability.abilityDelegatorRegistry';
import { ApiClient, HttpRequest, HttpResponse, HttpTransport, SessionProvider } from '../../../main/ets/core/api/ApiClient';
import { PlaybackManifest, SubtitleOption, TokenPair } from '../../../main/ets/core/api/ApiModels';
import { SubtitleCache } from '../../../main/ets/core/storage/SubtitleCache';
import { TrackInfo, TrackSource, TrackStore } from '../../../main/ets/features/playback/TrackStore';

const SUB_A = '50000000-0000-0000-0000-0000000000a1';
const SUB_B = '50000000-0000-0000-0000-0000000000a2';

class FakeSession implements SessionProvider {
  getAccessToken(): string | null {
    return 'fake-access';
  }

  getRefreshToken(): string | null {
    return 'fake-refresh';
  }

  setTokens(pair: TokenPair): Promise<void> {
    return Promise.resolve();
  }

  clearTokens(): Promise<void> {
    return Promise.resolve();
  }
}

class FakeTransport implements HttpTransport {
  request(request: HttpRequest): Promise<HttpResponse> {
    if (request.url.includes('/playback/subtitles/')) {
      const body = request.url.includes(SUB_B) ? 'B' : 'A';
      const ok: HttpResponse = { statusCode: 200, body: `1\n00:00:00,000 --> 00:00:02,000\n${body}` };
      return Promise.resolve(ok);
    }
    return Promise.reject(new Error(`no route for ${request.url}`));
  }
}

class FakeTrackSource implements TrackSource {
  tracks: TrackInfo[] = [];
  selected: number[] = [];
  deselected: number[] = [];
  addedUrls: string[] = [];
  getTracksError: Error | null = null;
  addSubtitleError: Error | null = null;

  getTracks(): Promise<TrackInfo[]> {
    if (this.getTracksError !== null) {
      return Promise.reject(this.getTracksError);
    }
    return Promise.resolve(this.tracks);
  }

  selectTrack(index: number): Promise<void> {
    this.selected.push(index);
    return Promise.resolve();
  }

  deselectTrack(index: number): Promise<void> {
    this.deselected.push(index);
    return Promise.resolve();
  }

  addSubtitle(url: string): Promise<void> {
    this.addedUrls.push(url);
    if (this.addSubtitleError !== null) {
      return Promise.reject(this.addSubtitleError);
    }
    return Promise.resolve();
  }
}

function subtitleJson(sub: SubtitleOption): string {
  return `{"id":"${sub.id}","media_id":null,"name":"${sub.name}","format":"${sub.format}",` +
    `"language":${sub.language === null ? 'null' : `"${sub.language}"`},"selected_by_default":${sub.selectedByDefault}}`;
}

function manifestWith(subtitles: SubtitleOption[]): PlaybackManifest {
  let subs = '[';
  for (let i = 0; i < subtitles.length; i++) {
    if (i > 0) {
      subs = subs + ',';
    }
    subs = subs + subtitleJson(subtitles[i]);
  }
  subs = subs + ']';
  return PlaybackManifest.fromText(
    `{"session_id":"20000000-0000-0000-0000-0000000000e1","cache_job_id":"10000000-0000-0000-0000-0000000000c1",` +
    `"mode":"original","platform":"harmonyos","stream_url":"/playback/streams/x",` +
    `"expires_at":"${new Date(Date.now() + 3600000).toISOString()}",` +
    `"subtitle_cache_expires_at":"${new Date(Date.now() + 3600000).toISOString()}",` +
    `"required_user_agent":"SakuraPlayer/1.0 (HarmonyOS)","embedded_tracks_source":"client_player",` +
    `"media_queue":[{"session_id":"20000000-0000-0000-0000-0000000000e1",` +
    `"media":{"id":"10000000-0000-0000-0000-0000000000d1"},"stream_url":"/s","sequence_no":1}],` +
    `"subtitles":${subs},"progress":null}`);
}

const sleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

export default function trackStoreTest() {
  describe('TrackStore', () => {
    it('enumerates_embedded_subtitles_and_audio_tracks', 0, async () => {
      const source = new FakeTrackSource();
      source.tracks = [
        new TrackInfo(0, 'video', 'Video'),
        new TrackInfo(1, 'audio', '日语'),
        new TrackInfo(2, 'audio', '中文'),
        new TrackInfo(3, 'subtitle', '简中'),
      ];
      const store = new TrackStore();
      store.attach(source, manifestWith([]));
      await store.refreshTracks(AbilityDelegatorRegistry.getAbilityDelegator().getAppContext(), null);
      expect(store.embeddedSubtitles.length).assertEqual(1);
      expect(store.embeddedSubtitles[0].index).assertEqual(3);
      expect(store.audioTracks.length).assertEqual(2);
      expect(store.tracksReady).assertTrue();
      // 选择内嵌字幕轨
      store.selectEmbedded(store.embeddedSubtitles[0]);
      expect(source.selected.length).assertEqual(1);
      expect(source.selected[0]).assertEqual(3);
      expect(store.selectedEmbeddedIndex).assertEqual(3);
    });

    it('no_embedded_tracks_keeps_lists_empty', 0, async () => {
      const source = new FakeTrackSource();
      source.tracks = [new TrackInfo(0, 'video', 'Video')];
      const store = new TrackStore();
      store.attach(source, manifestWith([]));
      await store.refreshTracks(AbilityDelegatorRegistry.getAbilityDelegator().getAppContext(), null);
      expect(store.embeddedSubtitles.length).assertEqual(0);
      expect(store.audioTracks.length).assertEqual(0);
    });

    it('track_enumeration_failure_does_not_block', 0, async () => {
      const source = new FakeTrackSource();
      source.getTracksError = new Error('enum failed');
      const store = new TrackStore();
      store.attach(source, manifestWith([]));
      await store.refreshTracks(AbilityDelegatorRegistry.getAbilityDelegator().getAppContext(), null);
      expect(store.embeddedSubtitles.length).assertEqual(0);
      expect(store.tracksReady).assertTrue();
    });

    it('downloads_external_default_subtitle_to_cache_and_loads', 0, async () => {
      const context = AbilityDelegatorRegistry.getAbilityDelegator().getAppContext();
      await SubtitleCache.clear(context);
      const client = new ApiClient(new FakeTransport(), 'http://test/api/v1', new FakeSession());
      const sub = new SubtitleOption(SUB_A, null, '默认字幕', 'srt', 'zh', true);
      const source = new FakeTrackSource();
      const store = new TrackStore();
      store.attach(source, manifestWith([sub]));
      await store.refreshTracks(context, client);
      expect(store.selectedExternalId).assertEqual(SUB_A);
      expect(source.addedUrls.length).assertEqual(1);
      expect(source.addedUrls[0]).assertEqual(`file://${SubtitleCache.pathFor(context, SUB_A, 'srt')}`);
      expect(SubtitleCache.exists(context, SUB_A)).assertTrue();
      await SubtitleCache.clear(context);
    });

    it('subtitle_load_failure_marks_error_but_tracks_ready', 0, async () => {
      const context = AbilityDelegatorRegistry.getAbilityDelegator().getAppContext();
      await SubtitleCache.clear(context);
      const client = new ApiClient(new FakeTransport(), 'http://test/api/v1', new FakeSession());
      const sub = new SubtitleOption('50000000-0000-0000-0000-0000000000c9', null, '缺', 'ass', 'zh', true);
      const source = new FakeTrackSource();
      // 下载成功但 addSubtitle 失败（格式不支持等）
      source.addSubtitleError = new Error('format unsupported');
      const store = new TrackStore();
      store.attach(source, manifestWith([sub]));
      await store.refreshTracks(context, client);
      expect(store.subtitleError).assertEqual('subtitle_load_failed');
      expect(store.tracksReady).assertTrue();
      // 视频不受影响（播放器无失败标记）
      expect(source.selected.length).assertEqual(0);
      await SubtitleCache.clear(context);
    });

    it('switches_between_multiple_external_subtitles', 0, async () => {
      const context = AbilityDelegatorRegistry.getAbilityDelegator().getAppContext();
      await SubtitleCache.clear(context);
      const client = new ApiClient(new FakeTransport(), 'http://test/api/v1', new FakeSession());
      const subA = new SubtitleOption(SUB_A, null, '字幕A', 'srt', 'zh', true);
      const subB = new SubtitleOption(SUB_B, null, '字幕B', 'vtt', 'zh', false);
      const source = new FakeTrackSource();
      const store = new TrackStore();
      store.attach(source, manifestWith([subA, subB]));
      await store.refreshTracks(context, client);
      expect(store.selectedExternalId).assertEqual(SUB_A);
      // 切换 B
      await store.selectExternal(context, client, subB);
      expect(store.selectedExternalId).assertEqual(SUB_B);
      expect(source.addedUrls.length).assertEqual(2);
      expect(source.addedUrls[1]).assertEqual(`file://${SubtitleCache.pathFor(context, SUB_B, 'vtt')}`);
      await SubtitleCache.clear(context);
    });

    it('select_embedded_clears_external_selection', 0, () => {
      const source = new FakeTrackSource();
      source.tracks = [new TrackInfo(1, 'subtitle', '内嵌')];
      const store = new TrackStore();
      store.attach(source, manifestWith([]));
      store.selectedExternalId = SUB_A;
      store.selectEmbedded(store.embeddedSubtitles[0] === undefined ?
        new TrackInfo(1, 'subtitle', '内嵌') : store.embeddedSubtitles[0]);
      expect(store.selectedExternalId).assertNull();
      expect(store.selectedEmbeddedIndex).assertEqual(1);
    });

    it('deselect_clears_embedded_and_external', 0, () => {
      const source = new FakeTrackSource();
      source.tracks = [new TrackInfo(2, 'subtitle', '内嵌')];
      const store = new TrackStore();
      store.attach(source, manifestWith([]));
      store.selectEmbedded(new TrackInfo(2, 'subtitle', '内嵌'));
      expect(source.selected.length).assertEqual(1);
      store.deselectSubtitle();
      expect(source.deselected.length).assertEqual(1);
      expect(store.selectedEmbeddedIndex).assertNull();
      expect(store.selectedExternalId).assertNull();
    });

    it('select_audio_switches_track', 0, () => {
      const source = new FakeTrackSource();
      const store = new TrackStore();
      store.attach(source, manifestWith([]));
      store.selectAudio(new TrackInfo(1, 'audio', '日语'));
      expect(source.selected.length).assertEqual(1);
      expect(source.selected[0]).assertEqual(1);
      expect(store.selectedAudioIndex).assertEqual(1);
    });
  });
}

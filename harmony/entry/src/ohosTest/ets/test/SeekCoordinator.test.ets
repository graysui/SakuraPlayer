/**
 * TASK-310 SeekCoordinator 测试：30-60 次连续 seek 首/末执行、错误清 pending、失败后恢复。
 */

import { describe, it, expect } from '@ohos/hypium';
import { SeekCallbacks, SeekCoordinator } from '../../../main/ets/features/playback/SeekCoordinator';

class Fixture {
  readonly seekCalls: number[];
  readonly coordinator: SeekCoordinator;
  readonly errors: Error[] = [];
  readonly done: number[] = [];

  constructor() {
    this.seekCalls = new Array<number>();
    const callbacks = new SeekCallbacks(
      (timeMs: number): void => {
        this.done.push(timeMs);
      },
      (err: Error): void => {
        this.errors.push(err);
      });
    this.coordinator = new SeekCoordinator((timeMs: number): void => {
      this.seekCalls.push(timeMs);
    }, callbacks);
  }
}

export default function seekCoordinatorTest() {
  describe('SeekCoordinator', () => {
    it('idle_executes_first_target_immediately', 0, () => {
      const fixture = new Fixture();
      fixture.coordinator.request(1000);
      expect(fixture.seekCalls.length).assertEqual(1);
      expect(fixture.seekCalls[0]).assertEqual(1000);
      expect(fixture.coordinator.isInflight).assertTrue();
    });

    it('inflight_overwrites_pending_target', 0, () => {
      const fixture = new Fixture();
      fixture.coordinator.request(1000);
      // 在途：三个目标只保留最后
      fixture.coordinator.request(2000);
      fixture.coordinator.request(3000);
      fixture.coordinator.request(4000);
      expect(fixture.seekCalls.length).assertEqual(1);
      expect(fixture.coordinator.pendingTarget).assertEqual(4000);
      // 完成首目标后执行最后 pending
      fixture.coordinator.onSeekDone();
      expect(fixture.seekCalls.length).assertEqual(2);
      expect(fixture.seekCalls[1]).assertEqual(4000);
      expect(fixture.coordinator.isInflight).assertTrue();
      // 完成最后目标 → 空闲
      fixture.coordinator.onSeekDone();
      expect(fixture.coordinator.isInflight).assertFalse();
    });

    it('no_pending_after_done_goes_idle', 0, () => {
      const fixture = new Fixture();
      fixture.coordinator.request(1000);
      fixture.coordinator.onSeekDone();
      expect(fixture.coordinator.isInflight).assertFalse();
      expect(fixture.seekCalls.length).assertEqual(1);
    });

    it('error_clears_pending_and_reports', 0, () => {
      const fixture = new Fixture();
      fixture.coordinator.request(1000);
      fixture.coordinator.request(2000);
      fixture.coordinator.request(3000);
      const err = new Error('seek failed');
      fixture.coordinator.onSeekError(err);
      expect(fixture.coordinator.isInflight).assertFalse();
      expect(fixture.coordinator.pendingTarget).assertNull();
      expect(fixture.errors.length).assertEqual(1);
      // 失败后新调用可恢复
      fixture.coordinator.request(5000);
      expect(fixture.seekCalls.length).assertEqual(2);
      expect(fixture.seekCalls[1]).assertEqual(5000);
    });

    it('high_frequency_30_targets_keeps_first_and_last', 0, () => {
      const fixture = new Fixture();
      fixture.coordinator.request(100);
      for (let i = 1; i < 30; i++) {
        fixture.coordinator.request(100 + i * 100);
      }
      // 在途期间 29 个目标被合并为最后一个
      expect(fixture.seekCalls.length).assertEqual(1);
      expect(fixture.seekCalls[0]).assertEqual(100);
      expect(fixture.coordinator.pendingTarget).assertEqual(100 + 29 * 100);
      fixture.coordinator.onSeekDone();
      expect(fixture.seekCalls.length).assertEqual(2);
      expect(fixture.seekCalls[1]).assertEqual(100 + 29 * 100);
      fixture.coordinator.onSeekDone();
      expect(fixture.coordinator.isInflight).assertFalse();
    });

    it('high_frequency_60_targets_series', 0, () => {
      const fixture = new Fixture();
      for (let round = 0; round < 2; round++) {
        fixture.coordinator.request(round * 60000);
        for (let i = 1; i < 60; i++) {
          fixture.coordinator.request(round * 60000 + i * 1000);
        }
        expect(fixture.seekCalls.length).assertEqual(round * 2 + 1);
        fixture.coordinator.onSeekDone();
        expect(fixture.seekCalls.length).assertEqual(round * 2 + 2);
        fixture.coordinator.onSeekDone();
      }
      expect(fixture.coordinator.isInflight).assertFalse();
      expect(fixture.seekCalls[0]).assertEqual(0);
      expect(fixture.seekCalls[1]).assertEqual(59000);
      expect(fixture.seekCalls[2]).assertEqual(60000);
      expect(fixture.seekCalls[3]).assertEqual(119000);
    });

    it('single_target_after_idle_executes_directly', 0, () => {
      const fixture = new Fixture();
      fixture.coordinator.request(5000);
      expect(fixture.seekCalls.length).assertEqual(1);
      fixture.coordinator.onSeekDone();
      expect(fixture.coordinator.isInflight).assertFalse();
      fixture.coordinator.request(9000);
      expect(fixture.seekCalls.length).assertEqual(2);
      expect(fixture.seekCalls[1]).assertEqual(9000);
    });

    it('negative_target_ignored', 0, () => {
      const fixture = new Fixture();
      fixture.coordinator.request(-100);
      expect(fixture.seekCalls.length).assertEqual(0);
      expect(fixture.coordinator.isInflight).assertFalse();
    });

    it('reset_clears_state', 0, () => {
      const fixture = new Fixture();
      fixture.coordinator.request(1000);
      fixture.coordinator.request(2000);
      fixture.coordinator.reset();
      expect(fixture.coordinator.isInflight).assertFalse();
      expect(fixture.coordinator.pendingTarget).assertNull();
      // reset 后新请求直接执行
      fixture.coordinator.request(3000);
      expect(fixture.seekCalls.length).assertEqual(2);
      expect(fixture.seekCalls[1]).assertEqual(3000);
    });
  });
}

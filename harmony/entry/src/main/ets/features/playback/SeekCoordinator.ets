/**
 * Seek 串行合并协调器（AC-105）。
 *
 * - 一次只执行一个 seek（seeker 端口）；空闲时执行首目标。
 * - 在途时只覆盖最后 pending 目标（中间目标丢弃）。
 * - 成功后执行 pending 目标；失败清空 pending 并把错误交给 onError。
 * - 只依赖 seek(timeMs) 端口，不接触 AVPlayer 直接 API。
 */

/** 协调器事件回调（页面/适配器注入；class 满足 ArkTS 无结构类型约束）。 */
export class SeekCallbacks {
  readonly onDone: (timeMs: number) => void;
  readonly onError: (err: Error) => void;

  constructor(onDone: (timeMs: number) => void, onError: (err: Error) => void) {
    this.onDone = onDone;
    this.onError = onError;
  }
}

export class SeekCoordinator {
  private readonly seekFn: (timeMs: number) => void;
  private readonly callbacks: SeekCallbacks;
  private inflight: boolean = false;
  private pending: number | null = null;
  private generation: number = 0;

  /** seekFn：发起一次 seek（timeMs 毫秒）；底层完成后必须调用 onSeekDone/onSeekError。 */
  constructor(seekFn: (timeMs: number) => void, callbacks: SeekCallbacks) {
    this.seekFn = seekFn;
    this.callbacks = callbacks;
  }

  /** 用户/自动续播只调用此入口（禁止直接访问底层 seek）。 */
  request(timeMs: number): void {
    if (timeMs < 0) {
      return;
    }
    if (!this.inflight) {
      this.inflight = true;
      this.pending = null;
      this.seekFn(timeMs);
      return;
    }
    // 在途：只覆盖最后 pending 目标
    this.pending = timeMs;
  }

  /** 底层 seek 完成（seekDone 事件）。 */
  onSeekDone(): void {
    if (!this.inflight) {
      return;
    }
    const next = this.pending;
    if (next === null) {
      this.inflight = false;
      return;
    }
    this.pending = null;
    this.seekFn(next);
  }

  /** 底层 seek 失败（error 事件）。 */
  onSeekError(err: Error): void {
    this.inflight = false;
    this.pending = null;
    this.callbacks.onError(err);
  }

  /** 播放器销毁/重载：清空状态。 */
  reset(): void {
    this.generation++;
    this.inflight = false;
    this.pending = null;
  }

  get isInflight(): boolean {
    return this.inflight;
  }

  get pendingTarget(): number | null {
    return this.pending;
  }
}

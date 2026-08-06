/**
 * 诊断页 Store（AC-119/120/121/122）。
 *
 * - 脱敏诊断：组件状态/队列/元数据聚合进度/最近失败/连接测试。
 * - 元数据领取暂停/恢复（PUT admin/metadata-queue，单一布尔，不中断运行中任务）。
 * - 失败任务完整重试（POST retry，新 queued attempt 不改写旧 attempt）。
 * - 富化重试：只显式选择失败/缺失的可选阶段（images/dmm/actor_map/gfriends/translation），
 *   永不重跑 javdb_core；默认不含 translation（付费 AI）。
 */

import { ApiClient } from '../../core/api/ApiClient';
import { ApiException, Diagnostics, MetadataJobFull, MetadataJobPage, MetadataQueueControl, MetadataRetryResult } from '../../core/api/ApiModels';

export enum DiagnosticsStatus {
  IDLE,
  LOADING,
  READY,
  FAILED,
}

@ObservedV2
export class DiagnosticsStore {
  @Trace status: DiagnosticsStatus = DiagnosticsStatus.IDLE;
  @Trace diagnostics: Diagnostics | null = null;
  @Trace paused: boolean = false;
  @Trace togglingPause: boolean = false;
  @Trace retryingJobId: string | null = null;
  @Trace retryError: string | null = null;
  @Trace retryFeedback: string | null = null;
  @Trace errorMessage: string | null = null;
  @Trace jobStatus: string | null = null;
  @Trace jobs: MetadataJobFull[] = [];
  @Trace jobCursor: string | null = null;
  @Trace loadingJobs: boolean = false;

  private apiClient: ApiClient | null = null;
  private generation: number = 0;
  private readonly changeListeners: (() => void)[] = [];

  /** 富化阶段固定集合（顺序即显示顺序）；javdb_core 永不出现。 */
  static readonly ENRICHMENT_STAGES: string[] = ['images', 'dmm', 'actor_map', 'gfriends', 'translation'];

  attach(client: ApiClient | null): void {
    this.apiClient = client;
  }

  addChangeListener(listener: () => void): void {
    if (!this.changeListeners.includes(listener)) {
      this.changeListeners.push(listener);
    }
  }

  removeChangeListener(listener: () => void): void {
    const index = this.changeListeners.indexOf(listener);
    if (index >= 0) {
      this.changeListeners.splice(index, 1);
    }
  }

  detach(): void {
    this.apiClient = null;
    this.generation++;
    this.status = DiagnosticsStatus.IDLE;
    this.diagnostics = null;
    this.togglingPause = false;
    this.retryingJobId = null;
    this.retryError = null;
    this.retryFeedback = null;
    this.errorMessage = null;
  }

  load(): void {
    const client = this.apiClient;
    if (client === null) {
      return;
    }
    const gen = ++this.generation;
    this.status = DiagnosticsStatus.LOADING;
    this.errorMessage = null;
    this.notifyChanged();
    client.getDiagnostics().then((diagnostics: Diagnostics) => {
      if (gen !== this.generation) {
        return;
      }
      this.diagnostics = diagnostics;
      this.paused = diagnostics.queues.metadataPaused;
      this.status = DiagnosticsStatus.READY;
      this.notifyChanged();
    }).catch((err: Error) => {
      if (gen !== this.generation) {
        return;
      }
      this.status = DiagnosticsStatus.FAILED;
      this.errorMessage = this.errorTextOf(err);
      this.notifyChanged();
    });
  }

  retry(): void {
    this.load();
  }

  /** 加载元数据任务（默认失败/警告，供富化重试）。 */
  loadJobs(status: string | null): void {
    const client = this.apiClient;
    if (client === null) {
      return;
    }
    const gen = this.generation;
    this.jobStatus = status;
    this.loadingJobs = true;
    this.notifyChanged();
    client.listMetadataJobs(status, null).then((page: MetadataJobPage) => {
      if (gen !== this.generation) {
        return;
      }
      this.jobs = page.items;
      this.jobCursor = page.nextCursor;
      this.loadingJobs = false;
      this.notifyChanged();
    }).catch((err: Error) => {
      if (gen !== this.generation) {
        return;
      }
      this.loadingJobs = false;
      this.errorMessage = this.errorTextOf(err);
      this.notifyChanged();
    });
  }

  /** 暂停/恢复元数据领取（单一布尔；不中断运行中任务）。 */
  togglePause(): void {
    const client = this.apiClient;
    if (client === null || this.togglingPause) {
      return;
    }
    const gen = this.generation;
    this.togglingPause = true;
    this.errorMessage = null;
    this.notifyChanged();
    client.setMetadataQueueControl(!this.paused).then((control: MetadataQueueControl) => {
      if (gen !== this.generation) {
        return;
      }
      this.paused = control.paused;
      this.togglingPause = false;
      this.load();
      this.notifyChanged();
    }).catch((err: Error) => {
      if (gen !== this.generation) {
        return;
      }
      this.togglingPause = false;
      this.errorMessage = this.errorTextOf(err);
      this.notifyChanged();
    });
  }

  /** 失败任务完整重试（201 新 queued attempt）。 */
  retryMetadataJob(metadataJobId: string): void {
    const client = this.apiClient;
    if (client === null || this.retryingJobId !== null) {
      return;
    }
    const gen = this.generation;
    this.retryingJobId = metadataJobId;
    this.retryError = null;
    this.retryFeedback = null;
    this.notifyChanged();
    client.retryMetadataJob(metadataJobId).then((result: MetadataRetryResult) => {
      if (gen !== this.generation) {
        return;
      }
      this.retryingJobId = null;
      this.retryFeedback = `已创建第 ${result.attemptNo} 次尝试`;
      this.load();
      this.notifyChanged();
    }).catch((err: Error) => {
      if (gen !== this.generation) {
        return;
      }
      this.retryingJobId = null;
      this.retryError = this.errorTextOf(err);
      this.notifyChanged();
    });
  }

  /** 富化重试：只运行显式选择的阶段（从不重跑 javdb_core）。 */
  retryEnrichment(metadataJobId: string, stages: string[]): void {
    const client = this.apiClient;
    if (client === null || this.retryingJobId !== null || stages.length === 0) {
      return;
    }
    const gen = this.generation;
    this.retryingJobId = metadataJobId;
    this.retryError = null;
    this.retryFeedback = null;
    this.notifyChanged();
    client.retryMetadataEnrichment(metadataJobId, stages).then((result: MetadataRetryResult) => {
      if (gen !== this.generation) {
        return;
      }
      this.retryingJobId = null;
      this.retryFeedback = `已加入富化重试（第 ${result.attemptNo} 次尝试）`;
      this.load();
      this.notifyChanged();
    }).catch((err: Error) => {
      if (gen !== this.generation) {
        return;
      }
      this.retryingJobId = null;
      this.retryError = this.errorTextOf(err);
      this.notifyChanged();
    });
  }

  /** 组件状态中文文案。 */
  static componentStatusText(status: string): string {
    if (status === 'healthy') {
      return '健康';
    }
    if (status === 'degraded') {
      return '部分异常';
    }
    if (status === 'unavailable') {
      return '不可用';
    }
    if (status === 'credentials_invalid') {
      return '凭据无效';
    }
    return '未知';
  }

  static syncStateText(status: string): string {
    if (status === 'never') {
      return '从未运行';
    }
    if (status === 'running') {
      return '同步中';
    }
    if (status === 'succeeded') {
      return '同步成功';
    }
    if (status === 'failed') {
      return '同步失败';
    }
    return status;
  }

  static stageText(stage: string): string {
    if (stage === 'images') {
      return '剧照';
    }
    if (stage === 'dmm') {
      return 'DMM 资料';
    }
    if (stage === 'actor_map') {
      return '演员映射';
    }
    if (stage === 'gfriends') {
      return 'GFriends 头像';
    }
    if (stage === 'translation') {
      return 'AI 翻译';
    }
    return stage;
  }

  private errorTextOf(err: Error): string {
    const code = this.errorCodeOf(err);
    if (code === 'metadata_job_no_retryable_enrichment') {
      return '该任务没有可重试的富化阶段';
    }
    if (code === 'metadata_job_already_active') {
      return '已有富化任务正在执行，请完成后再试';
    }
    if (code === 'client_transport_error') {
      return '无法连接服务器，请稍后重试';
    }
    return '操作失败，请重试';
  }

  private errorCodeOf(err: Error): string {
    if (err instanceof ApiException) {
      return err.code;
    }
    return 'client_transport_error';
  }

  private notifyChanged(): void {
    for (const listener of this.changeListeners) {
      listener();
    }
  }
}

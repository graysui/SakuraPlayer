/**
 * 诊断页（AC-119/120/121/122）。
 * - 组件状态（≤10）/队列计数/元数据聚合进度（当前最多 3 番号）/最近失败（≤100）/连接测试（≤5）。
 * - 暂停/恢复元数据领取（单一布尔，不中断运行中任务）。
 * - 失败/警告任务显式富化重试：只选失败或缺失的可选阶段（默认不含 AI 翻译），
 *   永不重跑 javdb_core；重试成功只显示新 queued attempt。
 */

import { DiagnosticsStatus, DiagnosticsStore } from './DiagnosticsStore';
import { ComponentDiagnostic, ConnectionTest, FailureDiagnostic, MetadataJobFull } from '../../core/api/ApiModels';
import { authStore } from '../../core/auth/AuthStore';

@Component
export struct DiagnosticsPage {
  private store: DiagnosticsStore = new DiagnosticsStore();
  private readonly onStoreChanged: () => void = (): void => this.syncFromStore();
  @State ready: boolean = false;
  @State failed: boolean = false;
  @State selectedStages: string[] = [];

  aboutToAppear(): void {
    this.store.attach(authStore.apiClientProvider);
    this.store.addChangeListener(this.onStoreChanged);
    if (this.store.status === DiagnosticsStatus.IDLE) {
      this.store.load();
    }
    if (this.store.jobs.length === 0) {
      this.store.loadJobs('failed');
    }
    this.syncFromStore();
  }

  aboutToDisappear(): void {
    this.store.removeChangeListener(this.onStoreChanged);
    this.store.detach();
  }

  private syncFromStore(): void {
    this.ready = this.store.status === DiagnosticsStatus.READY;
    this.failed = this.store.status === DiagnosticsStatus.FAILED;
  }

  static connectionStatusOf(status: string): string {
    if (status === 'available') {
      return '连接正常';
    }
    if (status === 'credentials_invalid') {
      return '凭据无效';
    }
    if (status === 'not_configured') {
      return '未配置';
    }
    return '连接失败';
  }

  private componentColor(status: string): string {
    if (status === 'healthy') {
      return '#12B76A';
    }
    if (status === 'degraded') {
      return '#F79009';
    }
    if (status === 'unavailable' || status === 'credentials_invalid') {
      return '#FF3B30';
    }
    return '#667085';
  }

  @Builder
  componentSection() {
    Column({ space: 8 }) {
      Text('组件状态')
        .fontSize(16)
        .fontWeight(FontWeight.Bold)
        .fontColor($r('app.color.text_primary'))
        .width('100%')
      if (this.store.diagnostics !== null) {
        Flex({ wrap: FlexWrap.Wrap }) {
          ForEach(this.store.diagnostics.components, (component: ComponentDiagnostic) => {
            Column({ space: 2 }) {
              Text(component.component)
                .fontSize(12)
                .fontColor($r('app.color.text_secondary'))
              Text(DiagnosticsStore.componentStatusText(component.status))
                .fontSize(13)
                .fontWeight(FontWeight.Medium)
                .fontColor(this.componentColor(component.status))
            }
            .padding({ left: 12, right: 12, top: 8, bottom: 8 })
            .borderRadius(8)
            .border({ width: 0.5, color: $r('app.color.divider') })
            .margin({ right: 8, bottom: 8 })
          }, (component: ComponentDiagnostic) => component.component)
        }
        .width('100%')
      }
    }
    .width('100%')
    .padding({ left: 16, right: 16, top: 12 })
  }

  @Builder
  queueSection() {
    Column({ space: 8 }) {
      Text('队列与进度')
        .fontSize(16)
        .fontWeight(FontWeight.Bold)
        .fontColor($r('app.color.text_primary'))
        .width('100%')
      if (this.store.diagnostics !== null) {
        Text(`元数据：排队 ${this.store.diagnostics.queues.metadataQueued} / 运行 ${this.store.diagnostics.queues.metadataRunning} / 暂停 ${this.store.diagnostics.queues.metadataPaused ? '是' : '否'}`)
          .fontSize(12)
          .fontColor($r('app.color.text_secondary'))
          .width('100%')
        Text(`缓存：排队 ${this.store.diagnostics.queues.cacheQueued} / 运行 ${this.store.diagnostics.queues.cacheRunning} / 就绪 ${this.store.diagnostics.queues.cacheReady}`)
          .fontSize(12)
          .fontColor($r('app.color.text_secondary'))
          .width('100%')
        Text(`元数据总体：${this.store.diagnostics.metadataProgress.total} 个（排队 ${this.store.diagnostics.metadataProgress.queued} / 运行 ${this.store.diagnostics.metadataProgress.running} / 完成 ${this.store.diagnostics.metadataProgress.completed} / 失败 ${this.store.diagnostics.metadataProgress.failed}）`)
          .fontSize(12)
          .fontColor($r('app.color.text_primary'))
          .width('100%')
        if (this.store.diagnostics.metadataProgress.currentNumbers.length > 0) {
          Row({ space: 6 }) {
            Text('当前：')
              .fontSize(12)
              .fontColor($r('app.color.text_secondary'))
            ForEach(this.store.diagnostics.metadataProgress.currentNumbers, (number: string) => {
              Text(number)
                .fontSize(12)
                .fontColor($r('app.color.primary'))
            }, (number: string) => number)
          }
          .width('100%')
        }
        Row({ space: 10 }) {
          Button(this.store.paused ? '开始刮削' : '暂停刮削')
            .fontSize(13)
            .backgroundColor(this.store.paused ? $r('app.color.primary') : $r('app.color.surface_alt'))
            .fontColor(this.store.paused ? '#FFFFFF' : $r('app.color.text_primary'))
            .enabled(!this.store.togglingPause)
            .onClick(() => this.store.togglePause())
        }
        .width('100%')
        .margin({ top: 4 })
      }
    }
    .width('100%')
    .padding({ left: 16, right: 16, top: 12 })
  }

  @Builder
  retryRow(job: MetadataJobFull) {
    Column({ space: 6 }) {
      Row({ space: 8 }) {
        Text(job.number)
          .fontSize(14)
          .fontWeight(FontWeight.Medium)
          .fontColor($r('app.color.text_primary'))
          .layoutWeight(1)
        Text(job.status === 'failed' ? '任务失败' : '有警告')
          .fontSize(12)
          .fontColor('#FF3B30')
        if (job.errorCode !== null) {
          Text(job.errorCode)
            .fontSize(11)
            .fontColor($r('app.color.text_secondary'))
            .maxLines(1)
            .textOverflow({ overflow: TextOverflow.Ellipsis })
        }
      }
      .width('100%')
      if (job.canRetryEnrichment()) {
        Row({ space: 6 }) {
          Text('富化重试：')
            .fontSize(12)
            .fontColor($r('app.color.text_secondary'))
          ForEach(DiagnosticsStore.ENRICHMENT_STAGES, (stage: string) => {
            if (job.retryableStages.includes(stage)) {
              Checkbox({ name: stage })
                .select(this.selectedStages.includes(stage))
                .onChange((checked: boolean) => {
                  this.toggleStage(stage, checked);
                })
              Text(DiagnosticsStore.stageText(stage))
                .fontSize(12)
                .fontColor($r('app.color.text_primary'))
            }
          }, (stage: string) => stage)
        }
        .width('100%')
        Button('提交富化重试')
          .fontSize(12)
          .enabled(this.store.retryingJobId === null && this.selectedStages.length > 0)
          .onClick(() => {
            this.store.retryEnrichment(job.id, this.selectedStages);
            this.selectedStages = [];
          })
      } else {
        Text('无可用富化阶段')
          .fontSize(12)
          .fontColor($r('app.color.text_secondary'))
      }
    }
    .width('100%')
    .padding({ top: 8, bottom: 8 })
    .border({ width: { bottom: 0.5 }, color: $r('app.color.divider') })
  }

  private toggleStage(stage: string, checked: boolean): void {
    const next = this.selectedStages.slice();
    const index = next.indexOf(stage);
    if (checked && index < 0) {
      next.push(stage);
    }
    if (!checked && index >= 0) {
      next.splice(index, 1);
    }
    this.selectedStages = next;
  }

  @Builder
  jobsSection() {
    Column({ space: 6 }) {
      Text('失败/警告元数据任务')
        .fontSize(16)
        .fontWeight(FontWeight.Bold)
        .fontColor($r('app.color.text_primary'))
        .width('100%')
      Row({ space: 8 }) {
        Button('失败')
          .fontSize(12)
          .backgroundColor(this.store.jobStatus === 'failed' ? $r('app.color.primary') : $r('app.color.surface_alt'))
          .fontColor(this.store.jobStatus === 'failed' ? '#FFFFFF' : $r('app.color.text_primary'))
          .onClick(() => { this.selectedStages = []; this.store.loadJobs('failed'); })
        Button('警告')
          .fontSize(12)
          .backgroundColor(this.store.jobStatus === 'completed_with_warnings' ? $r('app.color.primary') : $r('app.color.surface_alt'))
          .fontColor(this.store.jobStatus === 'completed_with_warnings' ? '#FFFFFF' : $r('app.color.text_primary'))
          .onClick(() => { this.selectedStages = []; this.store.loadJobs('completed_with_warnings'); })
      }
      .width('100%')
      if (this.store.jobs.length === 0) {
        Text(this.store.loadingJobs ? '加载中…' : '暂无任务')
          .fontSize(12)
          .fontColor($r('app.color.text_secondary'))
          .width('100%')
          .padding({ top: 8, bottom: 8 })
      } else {
        ForEach(this.store.jobs, (job: MetadataJobFull) => {
          this.retryRow(job)
        }, (job: MetadataJobFull) => job.id)
      }
    }
    .width('100%')
    .padding({ left: 16, right: 16, top: 12 })
  }

  @Builder
  failuresSection() {
    Column({ space: 6 }) {
      Text('最近失败')
        .fontSize(16)
        .fontWeight(FontWeight.Bold)
        .fontColor($r('app.color.text_primary'))
        .width('100%')
      if (this.store.diagnostics !== null && this.store.diagnostics.recentFailures.length > 0) {
        ForEach(this.store.diagnostics.recentFailures, (failure: FailureDiagnostic) => {
          Row({ space: 8 }) {
            Text(failure.taskType === 'metadata' ? '元数据' : '缓存')
              .fontSize(12)
              .fontColor($r('app.color.text_secondary'))
            Text(failure.errorCode)
              .fontSize(12)
              .fontColor('#FF3B30')
              .layoutWeight(1)
              .maxLines(1)
              .textOverflow({ overflow: TextOverflow.Ellipsis })
            Text(`第 ${failure.attemptNo} 次`)
              .fontSize(11)
              .fontColor($r('app.color.text_secondary'))
          }
          .width('100%')
          .padding({ top: 6, bottom: 6 })
          .border({ width: { bottom: 0.5 }, color: $r('app.color.divider') })
        }, (failure: FailureDiagnostic) => failure.taskId)
      } else {
        Text('暂无失败记录')
          .fontSize(12)
          .fontColor($r('app.color.text_secondary'))
      }
    }
    .width('100%')
    .padding({ left: 16, right: 16, top: 12 })
  }

  @Builder
  connectionsSection() {
    Column({ space: 6 }) {
      Text('连接测试')
        .fontSize(16)
        .fontWeight(FontWeight.Bold)
        .fontColor($r('app.color.text_primary'))
        .width('100%')
      if (this.store.diagnostics !== null) {
        ForEach(this.store.diagnostics.connectionTests, (test: ConnectionTest) => {
          Row({ space: 8 }) {
            Text(test.target)
              .fontSize(12)
              .fontColor($r('app.color.text_secondary'))
            Text(DiagnosticsPage.connectionStatusOf(test.status))
              .fontSize(12)
              .fontColor(this.componentColor(test.status === 'available' ? 'healthy' : 'unavailable'))
              .layoutWeight(1)
            if (test.errorCode !== null) {
              Text(test.errorCode)
                .fontSize(11)
                .fontColor($r('app.color.text_secondary'))
                .maxLines(1)
                .textOverflow({ overflow: TextOverflow.Ellipsis })
            }
            Text(`${test.elapsedMs}ms`)
              .fontSize(11)
              .fontColor($r('app.color.text_secondary'))
          }
          .width('100%')
        }, (test: ConnectionTest) => test.target)
      }
    }
    .width('100%')
    .padding({ left: 16, right: 16, top: 12 })
  }

  build() {
    Scroll() {
      Column({ space: 0 }) {
        if (this.failed) {
          Column({ space: 10 }) {
            Text(this.store.errorMessage ?? '诊断加载失败')
              .fontSize(14)
              .fontColor($r('app.color.text_primary'))
            Button('重试')
              .fontSize(14)
              .onClick(() => this.store.retry())
          }
          .justifyContent(FlexAlign.Center)
          .width('100%')
          .height('70%')
        } else {
          this.componentSection()
          this.queueSection()
          this.jobsSection()
          this.failuresSection()
          this.connectionsSection()
        }
        if (this.store.retryFeedback !== null) {
          Text(this.store.retryFeedback)
            .fontSize(12)
            .fontColor($r('app.color.primary'))
            .width('100%')
            .padding({ left: 16, right: 16, top: 8 })
        }
        if (this.store.retryError !== null) {
          Text(this.store.retryError)
            .fontSize(12)
            .fontColor('#FF3B30')
            .width('100%')
            .padding({ left: 16, right: 16, top: 8, bottom: 24 })
        }
      }
      .width('100%')
    }
    .width('100%')
    .height('100%')
    .scrollBar(BarState.Off)
    .align(Alignment.Top)
  }
}

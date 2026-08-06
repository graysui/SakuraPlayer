/**
 * 设置页（AC-013/016/094/119/120/121）。
 *
 * - 115 绑定：active 显示脱敏账号/缓存根 + 解绑（二次确认）；unbound/expired/detached 扫码；
 *   QR 只存内存；credentials_expired 与 unavailable 文案分离。
 * - TTL 1..168 步进保存；固定容量 20/3/600 只读；JavDB/AI/MGDB CAS replace/clear；
 *   连接测试 5 目标；同步状态只读；诊断入口。
 * - 主密钥/密码/API key 不回显（只显示 configured）。
 */

import { util } from '@kit.ArkTS';
import { image } from '@kit.ImageKit';
import { QrBindingStatus, qrBindingStore } from './QrBindingStore';
import { SettingsStatus, SettingsStore } from './SettingsStore';
import { authStore } from '../../core/auth/AuthStore';
import { ConnectionTest } from '../../core/api/ApiModels';

function decodeBase64ToBytes(base64: string): ArrayBuffer {
  // ArkTS 无 Buffer/atob：用 util.Base64Helper
  const base64Helper = new util.Base64Helper();
  return base64Helper.decodeSync(base64).buffer;
}

@Component
export struct SettingsPage {
  @Require pathStack: NavPathStack;
  private settingsStore: SettingsStore = new SettingsStore();
  private readonly onStoreChanged: () => void = (): void => this.syncFromStore();
  private readonly onQrChanged: () => void = (): void => this.syncFromQr();

  @State settingsReady: boolean = false;
  @State settingsFailed: boolean = false;
  @State errorMessage: string | null = null;
  @State ttlText: string = '24';
  @State qrPixelMap: image.PixelMap | null = null;

  aboutToAppear(): void {
    qrBindingStore.attach(authStore.apiClientProvider);
    qrBindingStore.addChangeListener(this.onQrChanged);
    this.settingsStore.attach(authStore.apiClientProvider);
    this.settingsStore.addChangeListener(this.onStoreChanged);
    if (qrBindingStore.binding === null) {
      qrBindingStore.loadBinding();
    }
    if (this.settingsStore.status === SettingsStatus.IDLE) {
      this.settingsStore.load();
    }
    this.syncFromStore();
    this.syncFromQr();
  }

  aboutToDisappear(): void {
    qrBindingStore.removeChangeListener(this.onQrChanged);
    qrBindingStore.detach();
    this.settingsStore.removeChangeListener(this.onStoreChanged);
    this.settingsStore.detach();
    this.releaseQrPixelMap();
  }

  private syncFromStore(): void {
    this.settingsReady = this.settingsStore.status === SettingsStatus.READY;
    this.settingsFailed = this.settingsStore.status === SettingsStatus.FAILED;
    this.errorMessage = this.settingsStore.errorMessage;
    this.ttlText = `${this.settingsStore.ttlInput}`;
  }

  private syncFromQr(): void {
    this.releaseQrPixelMap();
    const png = qrBindingStore.qrPngBase64;
    if (png !== null && qrBindingStore.status === QrBindingStatus.POLLING) {
      try {
        const bytes = decodeBase64ToBytes(png);
        const source = image.createImageSource(bytes);
        source.createPixelMap().then((pixelMap: image.PixelMap) => {
          this.qrPixelMap = pixelMap;
          source.release();
        }).catch(() => {
          source.release();
        });
      } catch (err) {
        // QR 解码失败：显示占位
      }
    }
  }

  private releaseQrPixelMap(): void {
    const current = this.qrPixelMap;
    if (current !== null) {
      try {
        current.release();
      } catch (err) {
        // 忽略释放异常
      }
      this.qrPixelMap = null;
    }
  }

  private qrStatusText(): string {
    const status = qrBindingStore.status;
    if (status === QrBindingStatus.CREATING) {
      return '正在生成二维码…';
    }
    if (status === QrBindingStatus.POLLING) {
      return '等待扫码';
    }
    if (status === QrBindingStatus.CONFIRMED) {
      return '绑定成功';
    }
    if (status === QrBindingStatus.EXPIRED) {
      return '二维码已过期，请重新扫码';
    }
    if (status === QrBindingStatus.CANCELED) {
      return '已取消扫码';
    }
    if (status === QrBindingStatus.CREDENTIALS_EXPIRED) {
      return '凭据已失效，请重新扫码';
    }
    if (status === QrBindingStatus.UNAVAILABLE) {
      return '115 暂时不可用，请稍后重试';
    }
    if (status === QrBindingStatus.FAILED) {
      return '操作失败，请重试';
    }
    return '';
  }

  @Builder
  qrSection() {
    Column({ space: 10 }) {
      Text('115 云盘')
        .fontSize(16)
        .fontWeight(FontWeight.Bold)
        .fontColor($r('app.color.text_primary'))
        .width('100%')
      if (qrBindingStore.binding !== null && qrBindingStore.binding.bound) {
        // active：显示脱敏账号 + 缓存根；unavailable 保留绑定提供重试
        Row({ space: 8 }) {
          SymbolGlyph($r('sys.symbol.checkmark'))
            .fontSize(18)
            .fontColor([$r('app.color.primary')])
          Column({ space: 2 }) {
            Text(`已绑定：${qrBindingStore.binding.displayName ?? '未知账号'}`)
              .fontSize(14)
              .fontColor($r('app.color.text_primary'))
            Text(qrBindingStore.binding.cacheRootReady ? '缓存根目录就绪' : '缓存根目录未就绪')
              .fontSize(12)
              .fontColor($r('app.color.text_secondary'))
          }
          .layoutWeight(1)
          .alignItems(HorizontalAlign.Start)
        }
        .width('100%')
        .padding(12)
        .backgroundColor($r('app.color.surface'))
        .borderRadius(8)
        Row({ space: 10 }) {
          if (qrBindingStore.binding.status === 'unavailable') {
            Button('重新检测')
              .fontSize(13)
              .backgroundColor($r('app.color.surface_alt'))
              .fontColor($r('app.color.text_primary'))
              .onClick(() => qrBindingStore.loadBinding())
          }
          Button('解除绑定')
            .fontSize(13)
            .backgroundColor('#FF3B30')
            .fontColor('#FFFFFF')
            .enabled(!qrBindingStore.unbinding)
            .onClick(() => this.confirmUnbind())
        }
        .width('100%')
      } else if (qrBindingStore.status === QrBindingStatus.POLLING && qrBindingStore.qrPngBase64 !== null) {
        // 扫码展示
        Column({ space: 8 }) {
          Stack() {
            if (this.qrPixelMap !== null) {
              Image(this.qrPixelMap)
                .width(180)
                .height(180)
            } else {
              Column() {
                Text('二维码加载中…')
                  .fontSize(12)
                  .fontColor($r('app.color.text_secondary'))
              }
              .justifyContent(FlexAlign.Center)
              .width(180)
              .height(180)
              .backgroundColor($r('app.color.surface_alt'))
            }
          }
          .width(180)
          .height(180)
          Text(this.qrStatusText())
            .fontSize(13)
            .fontColor($r('app.color.text_secondary'))
          Button('取消扫码')
            .fontSize(13)
            .backgroundColor($r('app.color.surface_alt'))
            .fontColor($r('app.color.text_primary'))
            .onClick(() => qrBindingStore.cancelQr())
        }
        .width('100%')
      } else {
        Column({ space: 8 }) {
          Text('未绑定 115 账号')
            .fontSize(14)
            .fontColor($r('app.color.text_primary'))
          if (qrBindingStore.status === QrBindingStatus.EXPIRED ||
            qrBindingStore.status === QrBindingStatus.CANCELED ||
            qrBindingStore.status === QrBindingStatus.CREDENTIALS_EXPIRED ||
            qrBindingStore.status === QrBindingStatus.FAILED ||
            qrBindingStore.status === QrBindingStatus.UNAVAILABLE) {
            Text(this.qrStatusText())
              .fontSize(12)
              .fontColor('#FF3B30')
          }
          Button('开始扫码')
            .fontSize(14)
            .enabled(qrBindingStore.status !== QrBindingStatus.CREATING)
            .onClick(() => qrBindingStore.startQr())
        }
        .width('100%')
      }
      if (qrBindingStore.errorMessage !== null) {
        Text(qrBindingStore.errorMessage)
          .fontSize(12)
          .fontColor('#FF3B30')
          .width('100%')
      }
    }
    .width('100%')
    .padding({ left: 16, right: 16, top: 12 })
  }

  private confirmUnbind(): void {
    this.getUIContext().getPromptAction().showDialog({
      title: '解除 115 绑定？',
      message: '活动缓存任务可能阻止解绑。',
      buttons: [
        { text: '取消', color: $r('app.color.text_secondary') },
        { text: '解除绑定', color: '#FF3B30' },
      ],
    }).then((result) => {
      if (result.index === 1) {
        qrBindingStore.unbind();
      }
    }).catch(() => {
      // 对话框关闭
    });
  }

  @Builder
  ttlSection() {
    Column({ space: 8 }) {
      Text('缓存期限')
        .fontSize(16)
        .fontWeight(FontWeight.Bold)
        .fontColor($r('app.color.text_primary'))
        .width('100%')
      Row({ space: 8 }) {
        Button('−')
          .fontSize(18)
          .width(40)
          .height(36)
          .onClick(() => {
            this.settingsStore.setTtlInput(Math.max(1, this.settingsStore.ttlInput - 1));
            this.ttlText = `${this.settingsStore.ttlInput}`;
          })
        TextInput({ text: this.ttlText })
          .type(InputType.Number)
          .width(90)
          .height(36)
          .onChange((value: string) => {
            this.ttlText = value;
            const parsed = Number(value);
            if (!Number.isNaN(parsed)) {
              this.settingsStore.setTtlInput(parsed);
            }
          })
        Button('＋')
          .fontSize(18)
          .width(40)
          .height(36)
          .onClick(() => {
            this.settingsStore.setTtlInput(Math.min(168, this.settingsStore.ttlInput + 1));
            this.ttlText = `${this.settingsStore.ttlInput}`;
          })
        Text('小时（1-168）')
          .fontSize(13)
          .fontColor($r('app.color.text_secondary'))
      }
      .width('100%')
      Button('保存')
        .fontSize(13)
        .enabled(!this.settingsStore.savingTtl)
        .onClick(() => {
          this.settingsStore.setTtlInput(Number(this.ttlText));
          this.settingsStore.saveTtl();
        })
    }
    .width('100%')
    .padding({ left: 16, right: 16, top: 12 })
  }

  @Builder
  readonlyConstants() {
    Row({ space: 16 }) {
      Text('就绪缓存上限：20')
        .fontSize(12)
        .fontColor($r('app.color.text_secondary'))
      Text('元数据并发：3')
        .fontSize(12)
        .fontColor($r('app.color.text_secondary'))
      Text('元数据超时：600 秒')
        .fontSize(12)
        .fontColor($r('app.color.text_secondary'))
    }
    .width('100%')
    .padding({ left: 16, right: 16, top: 8 })
  }

  @Builder
  javdbSection() {
    Column({ space: 8 }) {
      Text('JavDB')
        .fontSize(16)
        .fontWeight(FontWeight.Bold)
        .fontColor($r('app.color.text_primary'))
        .width('100%')
      if (this.settingsStore.settings !== null) {
        Text(`密码已配置：${this.settingsStore.settings.javdb.passwordConfigured ? '是' : '否'}`)
          .fontSize(12)
          .fontColor($r('app.color.text_secondary'))
          .width('100%')
        TextInput({ text: this.settingsStore.javdbUsername, placeholder: '用户名（可留空）' })
          .width('100%')
          .onChange((value: string) => {
            this.settingsStore.javdbUsername = value;
          })
        TextInput({ placeholder: '新密码' })
          .type(InputType.Password)
          .width('100%')
          .onChange((value: string) => {
            this.settingsStore.javdbPassword = value;
          })
        Row({ space: 10 }) {
          Button('保存')
            .fontSize(13)
            .enabled(!this.settingsStore.savingJavdb)
            .onClick(() => this.settingsStore.saveJavdb())
          Button('清除')
            .fontSize(13)
            .backgroundColor($r('app.color.surface_alt'))
            .fontColor($r('app.color.text_primary'))
            .enabled(this.settingsStore.settings.javdb.version >= 1 && !this.settingsStore.savingJavdb)
            .onClick(() => this.settingsStore.clearJavdb())
        }
        .width('100%')
      }
    }
    .width('100%')
    .padding({ left: 16, right: 16, top: 12 })
  }

  @Builder
  aiSection() {
    Column({ space: 8 }) {
      Text('AI 翻译')
        .fontSize(16)
        .fontWeight(FontWeight.Bold)
        .fontColor($r('app.color.text_primary'))
        .width('100%')
      if (this.settingsStore.settings !== null) {
        Text(`API Key 已配置：${this.settingsStore.settings.ai.apiKeyConfigured ? '是' : '否'}`)
          .fontSize(12)
          .fontColor($r('app.color.text_secondary'))
          .width('100%')
        TextInput({ text: this.settingsStore.aiBaseUrl, placeholder: 'Base URL' })
          .width('100%')
          .onChange((value: string) => {
            this.settingsStore.aiBaseUrl = value;
          })
        TextInput({ text: this.settingsStore.aiModel, placeholder: '模型' })
          .width('100%')
          .onChange((value: string) => {
            this.settingsStore.aiModel = value;
          })
        TextInput({ text: this.settingsStore.aiTimeout, placeholder: '超时（秒）' })
          .type(InputType.Number)
          .width('100%')
          .onChange((value: string) => {
            this.settingsStore.aiTimeout = value;
          })
        TextInput({ placeholder: '新 API Key' })
          .type(InputType.Password)
          .width('100%')
          .onChange((value: string) => {
            this.settingsStore.aiApiKey = value;
          })
        Row({ space: 10 }) {
          Button('保存')
            .fontSize(13)
            .enabled(!this.settingsStore.savingAi)
            .onClick(() => this.settingsStore.saveAi())
          Button('清除')
            .fontSize(13)
            .backgroundColor($r('app.color.surface_alt'))
            .fontColor($r('app.color.text_primary'))
            .enabled(this.settingsStore.settings.ai.version >= 1 && !this.settingsStore.savingAi)
            .onClick(() => this.settingsStore.clearAi())
        }
        .width('100%')
      }
    }
    .width('100%')
    .padding({ left: 16, right: 16, top: 12 })
  }

  @Builder
  mgdbSection() {
    Column({ space: 8 }) {
      Text('MGDB 数据源')
        .fontSize(16)
        .fontWeight(FontWeight.Bold)
        .fontColor($r('app.color.text_primary'))
        .width('100%')
      if (this.settingsStore.settings !== null) {
        Text(`已配置：${this.settingsStore.settings.mgdb.configured ? '是' : '否'}`)
          .fontSize(12)
          .fontColor($r('app.color.text_secondary'))
          .width('100%')
        TextInput({ text: this.settingsStore.mgdbSourceUrl, placeholder: 'GitHub 仓库 HTTPS 地址' })
          .width('100%')
          .onChange((value: string) => {
            this.settingsStore.mgdbSourceUrl = value;
          })
        Row({ space: 10 }) {
          Button('保存')
            .fontSize(13)
            .enabled(!this.settingsStore.savingMgdb)
            .onClick(() => this.settingsStore.saveMgdb())
          Button('清除')
            .fontSize(13)
            .backgroundColor($r('app.color.surface_alt'))
            .fontColor($r('app.color.text_primary'))
            .enabled(this.settingsStore.settings.mgdb.version >= 1 && !this.settingsStore.savingMgdb)
            .onClick(() => this.settingsStore.clearMgdb())
          Button('立即全量同步')
            .fontSize(12)
            .enabled(!this.settingsStore.syncingMgdb && this.settingsStore.settings.mgdb.configured)
            .onClick(() => this.settingsStore.requestFullSync())
        }
        .width('100%')
        if (this.settingsStore.mgdbSyncFeedback !== null) {
          Text(this.settingsStore.mgdbSyncFeedback)
            .fontSize(12)
            .fontColor($r('app.color.primary'))
        }
      }
    }
    .width('100%')
    .padding({ left: 16, right: 16, top: 12 })
  }

  @Builder
  syncSection() {
    Column({ space: 6 }) {
      Text('同步状态')
        .fontSize(16)
        .fontWeight(FontWeight.Bold)
        .fontColor($r('app.color.text_primary'))
        .width('100%')
      if (this.settingsStore.settings !== null) {
        Text(`30 天增量：${SettingsStore.syncStateTextSafe(this.settingsStore.settings.avdbSync.incremental30d.status)}（已导入 ${this.settingsStore.settings.avdbSync.incremental30d.importedCount}）`)
          .fontSize(12)
          .fontColor($r('app.color.text_secondary'))
          .width('100%')
        Text(`全量对账：${SettingsStore.syncStateTextSafe(this.settingsStore.settings.avdbSync.fullReconcile.status)}（已导入 ${this.settingsStore.settings.avdbSync.fullReconcile.importedCount}）`)
          .fontSize(12)
          .fontColor($r('app.color.text_secondary'))
          .width('100%')
      }
    }
    .width('100%')
    .padding({ left: 16, right: 16, top: 12 })
  }

  @Builder
  connectionSection() {
    Column({ space: 8 }) {
      Text('连接测试')
        .fontSize(16)
        .fontWeight(FontWeight.Bold)
        .fontColor($r('app.color.text_primary'))
        .width('100%')
      Flex({ wrap: FlexWrap.Wrap }) {
        ForEach(['cloud115', 'javdb', 'dmm', 'gfriends', 'ai'], (target: string) => {
          Column({ space: 2 }) {
            Button(this.targetLabel(target))
              .fontSize(12)
              .enabled(this.settingsStore.testingTarget === null)
              .onClick(() => this.settingsStore.testConnection(target))
            if (this.settingsStore.connectionResults.get(target) !== undefined) {
              Text(SettingsStore.connectionStatusText(this.settingsStore.connectionResults.get(target)))
                .fontSize(10)
                .fontColor($r('app.color.text_secondary'))
            }
          }
          .margin({ right: 8, bottom: 8 })
        }, (target: string) => target)
      }
      .width('100%')
    }
    .width('100%')
    .padding({ left: 16, right: 16, top: 12 })
  }

  private targetLabel(target: string): string {
    if (target === 'cloud115') {
      return '115';
    }
    if (target === 'javdb') {
      return 'JavDB';
    }
    if (target === 'dmm') {
      return 'DMM';
    }
    if (target === 'gfriends') {
      return 'GFriends';
    }
    return 'AI';
  }

  @Builder
  diagnosticsEntry() {
    Button('诊断信息')
      .fontSize(14)
      .width('100%')
      .margin({ top: 8 })
      .onClick(() => {
        this.pathStack.pushPath({ name: 'Diagnostics' });
      })
  }

  build() {
    Scroll() {
      Column({ space: 0 }) {
        if (this.settingsFailed) {
          Column({ space: 10 }) {
            Text('设置加载失败')
              .fontSize(15)
              .fontColor($r('app.color.text_primary'))
            Button('重试')
              .fontSize(14)
              .onClick(() => this.settingsStore.retry())
          }
          .justifyContent(FlexAlign.Center)
          .width('100%')
          .height(200)
        } else {
          this.qrSection()
          this.ttlSection()
          this.readonlyConstants()
          this.javdbSection()
          this.aiSection()
          this.mgdbSection()
          this.syncSection()
          this.connectionSection()
          if (this.errorMessage !== null) {
            Text(this.errorMessage)
              .fontSize(12)
              .fontColor('#FF3B30')
              .width('100%')
              .padding({ left: 16, right: 16, top: 8 })
          }
        }
        this.diagnosticsEntry()
        Text('主密钥不可编辑：启动级凭据仅由安装时配置')
          .fontSize(11)
          .fontColor($r('app.color.text_secondary'))
          .width('100%')
          .padding({ left: 16, right: 16, top: 8, bottom: 24 })
      }
      .id('settings_placeholder')
      .width('100%')
    }
    .width('100%')
    .height('100%')
    .scrollBar(BarState.Off)
    .align(Alignment.Top)
  }
}

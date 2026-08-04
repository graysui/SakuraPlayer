/**
 * 登录与后端基址配置页（AC-133/AC-135）。
 *
 * - 无已存基址：输入地址 → 校验/连接测试 → 保存。
 * - 私网明文 http：弹确认对话框，确认后才保存。
 * - bootstrapRequired：显示一次性初始化口令输入框（仅内存，发送后立即清空）。
 * - 已认证：显示会话状态与退出。
 */

import { authStore, AuthStatus } from '../../core/auth/AuthStore';

@Component
export struct AuthPage {
  private static readonly BOOTSTRAP_TOKEN_PATTERN: RegExp = /^[A-Za-z0-9_-]{43,512}$/;

  @State addressInput: string = '';
  @State tokenInput: string = '';
  @State usernameInput: string = '';
  @State passwordInput: string = '';
  @State showPrivateHttpConfirm: boolean = false;

  aboutToAppear(): void {
    if (authStore.serverBaseUrl.length > 0) {
      this.addressInput = authStore.serverBaseUrl;
    }
  }

  private onSaveAddress(): void {
    if (this.addressInput.trim().length === 0) {
      return;
    }
    authStore.configureServer(this.addressInput.trim());
    if (authStore.pendingPrivateHttp !== null) {
      this.showPrivateHttpConfirm = true;
    }
  }

  private onConfirmPrivateHttp(): void {
    this.showPrivateHttpConfirm = false;
    authStore.confirmPrivateHttp();
  }

  private onCancelPrivateHttp(): void {
    this.showPrivateHttpConfirm = false;
    authStore.cancelPrivateHttp();
  }

  private onSubmit(): void {
    if (authStore.bootstrapRequired) {
      const token = this.tokenInput.trim();
      // AC-133：初始化口令本地校验（43..512，^[A-Za-z0-9_-]+$），失败不发送
      if (!AuthPage.BOOTSTRAP_TOKEN_PATTERN.test(token) || this.usernameInput.length === 0) {
        return;
      }
      authStore.submitBootstrap(token, this.usernameInput, this.passwordInput);
      // 口令与密码只在本次调用栈内使用：发送后立即清空内存输入
      this.tokenInput = '';
      this.passwordInput = '';
      return;
    }
    if (this.usernameInput.length === 0) {
      return;
    }
    authStore.submitLogin(this.usernameInput, this.passwordInput);
    this.passwordInput = '';
  }

  @Builder
  errorBanner() {
    if (authStore.errorMessage !== null) {
      Text(authStore.errorMessage)
        .fontSize(13)
        .fontColor('#FF3B30')
        .padding(10)
        .borderRadius(8)
        .backgroundColor('#1AFF3B30')
        .width('100%')
        .margin({ bottom: 8 })
    }
  }

  @Builder
  addressSection() {
    Column({ space: 10 }) {
      Text('后端地址')
        .fontSize(16)
        .fontWeight(FontWeight.Bold)
        .alignSelf(ItemAlign.Start)
      TextInput({ placeholder: 'http(s)://主机:端口', text: $$this.addressInput })
        .type(InputType.URL)
        .width('100%')
      Button('保存并测试连接')
        .width('100%')
        .onClick(() => this.onSaveAddress())
      if (authStore.serverBaseUrl.length > 0) {
        Text(`当前地址：${authStore.serverBaseUrl}`)
          .fontSize(12)
          .fontColor('#66000000')
          .alignSelf(ItemAlign.Start)
      }
    }
    .width('100%')
  }

  @Builder
  credentialSection() {
    Column({ space: 10 }) {
      if (authStore.bootstrapRequired) {
        Text('初始化口令（一次性，仅本次发送）')
          .fontSize(14)
          .alignSelf(ItemAlign.Start)
        TextInput({ placeholder: '43..512 字符初始化口令', text: $$this.tokenInput })
          .type(InputType.Password)
          .width('100%')
      }
      TextInput({ placeholder: '管理员用户名', text: $$this.usernameInput })
        .type(InputType.USER_NAME)
        .width('100%')
      TextInput({ placeholder: '密码', text: $$this.passwordInput })
        .type(InputType.Password)
        .width('100%')
      Button(authStore.bootstrapRequired ? '创建管理员并登录' : '登录')
        .width('100%')
        .enabled(!authStore.busy)
        .onClick(() => this.onSubmit())
    }
    .width('100%')
  }

  @Builder
  authenticatedSection() {
    Column({ space: 12 }) {
      Text('已登录')
        .fontSize(18)
        .fontWeight(FontWeight.Bold)
      Text(authStore.serverBaseUrl)
        .fontSize(13)
        .fontColor('#66000000')
      Button('退出登录')
        .width('100%')
        .backgroundColor('#FF3B30')
        .onClick(() => {
          authStore.logout();
        })
    }
    .width('100%')
  }

  build() {
    Column() {
      Text('SakuraPlayer')
        .fontSize(26)
        .fontWeight(FontWeight.Bold)
        .margin({ top: 48, bottom: 24 })
      if (authStore.busy) {
        LoadingProgress()
          .width(32)
          .height(32)
          .margin({ bottom: 16 })
      }
      this.errorBanner()
      if (authStore.status === AuthStatus.AUTHENTICATED) {
        this.authenticatedSection()
      } else {
        Scroll() {
          Column({ space: 24 }) {
            this.addressSection()
            if (authStore.status === AuthStatus.UNAUTHENTICATED) {
              this.credentialSection()
            }
          }
          .width('100%')
          .padding(24)
        }
        .layoutWeight(1)
      }
    }
    .width('100%')
    .height('100%')
    .backgroundColor('#F5F6F8')
    .alignItems(HorizontalAlign.Center)
    .bindContentCover($$this.showPrivateHttpConfirm, this.privateHttpDialog(), {
      modalTransition: ModalTransition.NONE
    })
  }

  @Builder
  privateHttpDialog() {
    Column({ space: 16 }) {
      Text('确认使用私网明文 HTTP？')
        .fontSize(17)
        .fontWeight(FontWeight.Bold)
      Text('该地址使用未加密 HTTP，仅在可信内网使用。')
        .fontSize(14)
        .fontColor('#66000000')
        .textAlign(TextAlign.Center)
      Row({ space: 12 }) {
        Button('取消')
          .layoutWeight(1)
          .backgroundColor('#E0E0E0')
          .fontColor('#000000')
          .onClick(() => this.onCancelPrivateHttp())
        Button('确认')
          .layoutWeight(1)
          .onClick(() => this.onConfirmPrivateHttp())
      }
      .width('100%')
    }
    .padding(24)
    .backgroundColor(Color.White)
    .borderRadius(16)
    .width('80%')
  }
}

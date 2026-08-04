/**
 * 入口页：按登录态分流。
 * - 未认证（初始/基址配置/登录）：AuthPage
 * - 已认证：AppNavigation（Navigation 组合根 + 底部三 Tab）
 * @Entry build 根必须是容器组件。
 */

import { authStore, AuthStatus } from '../core/auth/AuthStore';
import { AuthPage } from '../features/auth/AuthPage';
import { AppNavigation } from '../app/AppNavigation';

@Entry
@Component
struct Index {
  build() {
    Column() {
      if (authStore.status === AuthStatus.AUTHENTICATED) {
        AppNavigation()
      } else {
        AuthPage()
      }
    }
    .width('100%')
    .height('100%')
  }
}

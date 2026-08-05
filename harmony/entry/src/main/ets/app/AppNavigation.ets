/**
 * Navigation 组合根（TASK-303 统一拥有）：
 * - 顶部栏：全局搜索入口 / 缓存角标（AC-118）/ 设置入口（AC-061）
 * - 底部三 Tab（媒体库/排行榜/女优，AC-059/060）
 * - 路由表：播放器（固定深色，AC-062）、设置、影片/女优详情、受限待补全详情
 * 各详情/设置页由后续任务填充，此处为占位。
 */

import { authStore, AuthStatus } from '../core/auth/AuthStore';
import { ActorSummary, MovieSummary, PendingMetadata } from '../core/api/ApiModels';
import { BottomTabs } from './BottomTabs';
import { CacheBadge } from '../features/cache/CacheBadge';
import { SearchOverlay } from '../features/search/SearchOverlay';
import { searchStore } from '../features/search/SearchStore';
import { LibraryPage } from '../features/library/LibraryPage';
import { libraryStore } from '../features/library/LibraryStore';

/** 播放器占位路由：固定深色背景（AC-062）。 */
@Builder
function PlayerRoute() {
  Column() {
    Text('播放器')
      .fontSize(16)
      .fontColor('#FFFFFF')
    Text('播放功能由 TASK-310/311 提供')
      .fontSize(12)
      .fontColor('#99FFFFFF')
      .margin({ top: 6 })
  }
  .justifyContent(FlexAlign.Center)
  .width('100%')
  .height('100%')
  .backgroundColor('#0B0C0E')
}

@Builder
function SettingsRoute() {
  Column() {
    Text('设置')
      .fontSize(16)
      .fontColor($r('app.color.text_primary'))
    Text('设置功能由 TASK-308 提供')
      .id('settings_placeholder')
      .fontSize(12)
      .fontColor($r('app.color.text_secondary'))
      .margin({ top: 6 })
  }
  .justifyContent(FlexAlign.Center)
  .width('100%')
  .height('100%')
}

@Builder
export function pageMapBuilder(name: string, param: Object) {
  if (name === 'Player') {
    NavDestination() {
      PlayerRoute()
    }
    .title('播放器')
    .backgroundColor($r('app.color.player_background'))
  } else if (name === 'Settings') {
    NavDestination() {
      SettingsRoute()
    }
    .title('设置')
  } else if (name === 'MovieDetail') {
    Column() {
      Text('影片详情（占位）')
        .fontSize(14)
        .fontColor($r('app.color.text_secondary'))
      if (param instanceof MovieSummary) {
        Text(`${param.number} ${param.title}`)
          .fontSize(16)
          .fontColor($r('app.color.text_primary'))
          .margin({ top: 8 })
      }
    }
    .justifyContent(FlexAlign.Center)
    .width('100%')
    .height('100%')
  } else if (name === 'ActorDetail') {
    Column() {
      Text('女优详情（占位）')
        .fontSize(14)
        .fontColor($r('app.color.text_secondary'))
      if (param instanceof ActorSummary) {
        Text(param.displayName)
          .fontSize(16)
          .fontColor($r('app.color.text_primary'))
          .margin({ top: 8 })
      }
    }
    .justifyContent(FlexAlign.Center)
    .width('100%')
    .height('100%')
  } else if (name === 'PendingDetail') {
    Column({ space: 8 }) {
      Text('待补全影片（受限详情）')
        .fontSize(14)
        .fontColor($r('app.color.text_secondary'))
      if (param instanceof PendingMetadata) {
        Text(param.number)
          .fontSize(18)
          .fontWeight(FontWeight.Bold)
          .fontColor($r('app.color.text_primary'))
        Text(param.state === 'failed' ? '补全失败' : (param.state === 'running' ? '正在补全' : '等待补全'))
          .fontSize(13)
          .fontColor(param.state === 'failed' ? '#FF3B30' : $r('app.color.text_secondary'))
      }
    }
    .justifyContent(FlexAlign.Center)
    .width('100%')
    .height('100%')
  } else {
    Column() {
      Text('未知页面')
        .fontSize(14)
        .fontColor($r('app.color.text_secondary'))
    }
    .justifyContent(FlexAlign.Center)
    .width('100%')
    .height('100%')
  }
}



@Component
export struct AppNavigation {
  private pathStack: NavPathStack = new NavPathStack();
  @State showSearch: boolean = false;

  aboutToAppear(): void {
    // 挂接全局搜索与媒体库到认证客户端与事件快照
    searchStore.attach(authStore.apiClientProvider, authStore.snapshotStore);
    libraryStore.attach(authStore.apiClientProvider);
  }

  aboutToDisappear(): void {
    searchStore.detach();
    libraryStore.detach();
  }

  @Builder
  topBar() {
    Row({ space: 12 }) {
      Text('搜索')
        .fontSize(14)
        .fontColor($r('app.color.primary'))
        .onClick(() => {
          this.showSearch = true;
        })
      Blank()
      CacheBadge({ snapshot: authStore.snapshotStore })
      Text('设置')
        .fontSize(14)
        .fontColor($r('app.color.primary'))
        .onClick(() => {
          this.pathStack.pushPath({ name: 'Settings' });
        })
    }
    .width('100%')
    .padding({ left: 16, right: 16, top: 8, bottom: 8 })
    .backgroundColor($r('app.color.surface'))
  }

  @Builder
  searchSheet() {
    SearchOverlay({ pathStack: this.pathStack })
  }

  build() {
    Navigation(this.pathStack) {
      Column() {
        this.topBar()
        BottomTabs()
      }
      .width('100%')
      .height('100%')
    }
    .mode(NavigationMode.Stack)
    .hideTitleBar(true)
    .navDestination(pageMapBuilder)
    .bindSheet($$this.showSearch, this.searchSheet(), {
      height: SheetSize.MEDIUM,
      detents: [SheetSize.MEDIUM, SheetSize.LARGE],
      showClose: true,
      title: { title: '全局搜索' },
      onDisappear: (): void => {
        searchStore.clear();
      },
    })
  }
}

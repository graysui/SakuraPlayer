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
import { rankingsStore } from '../features/rankings/RankingsStore';
import { ActorDetailPage } from '../features/actors/ActorDetailPage';
import { MovieDetailPage } from '../features/movies/MovieDetailPage';
import { appNotifications } from '../core/notifications/AppNotifications';
import { SettingsPage } from '../features/settings/SettingsPage';
import { DiagnosticsPage } from '../features/settings/DiagnosticsPage';
import { CachePage } from '../features/cache/CachePage';
import { BlockingWaitPage } from '../features/cache/BlockingWaitPage';
import { PlayerPage } from '../features/playback/PlayerPage';
import { actorsStore } from '../features/actors/ActorsStore';

@Builder
function SettingsRoute(pathStack: NavPathStack) {
  SettingsPage({ pathStack: pathStack })
}

/** 模块级路由 builder 使用的 pathStack（由 AppNavigation aboutToAppear 注入）。 */
let appNavigationPathStack: NavPathStack | null = null;

@Builder
export function pageMapBuilder(name: string, param: Object) {
  if (name === 'Player') {
    NavDestination() {
      if (param instanceof Object && (param as Record<string, Object>)['cacheJobId'] !== undefined &&
        appNavigationPathStack !== null) {
        PlayerPage({
          cacheJobId: String((param as Record<string, Object>)['cacheJobId']),
          mediaId: (param as Record<string, Object>)['mediaId'] === null ? '' :
            String((param as Record<string, Object>)['mediaId']),
          pathStack: appNavigationPathStack,
        })
      }
    }
    .title('播放器')
    .backgroundColor($r('app.color.player_background'))
  } else if (name === 'Settings') {
    NavDestination() {
      if (appNavigationPathStack !== null) {
        SettingsRoute(appNavigationPathStack)
      }
    }
    .title('设置')
  } else if (name === 'Diagnostics') {
    NavDestination() {
      DiagnosticsPage()
    }
    .title('诊断')
  } else if (name === 'Cache') {
    NavDestination() {
      CachePage()
    }
    .title('缓存任务')
  } else if (name === 'BlockingWait') {
    if (appNavigationPathStack !== null) {
      BlockingWaitPage({ pathStack: appNavigationPathStack })
    }
  } else if (name === 'MovieDetail') {
    NavDestination() {
      if (param instanceof MovieSummary && appNavigationPathStack !== null) {
        MovieDetailPage({ movieId: param.id, summary: param, pathStack: appNavigationPathStack })
      }
    }
    .title('影片详情')
    .backgroundColor($r('app.color.background'))
  } else if (name === 'ActorDetail') {
    NavDestination() {
      if (param instanceof ActorSummary && appNavigationPathStack !== null) {
        ActorDetailPage({ actorId: param.id, summary: param, pathStack: appNavigationPathStack })
      }
    }
    .title('女优详情')
    .backgroundColor($r('app.color.background'))
  } else if (name === 'PendingDetail') {
    NavDestination() {
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
    }
    .title('待补全影片')
    .backgroundColor($r('app.color.background'))
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
    // 模块级路由 builder 需要 pathStack 转发（ActorDetail 内关联影片 push）
    appNavigationPathStack = this.pathStack;
    // 挂接全局搜索与媒体库/排行榜/女优到认证客户端与事件快照
    searchStore.attach(authStore.apiClientProvider, authStore.snapshotStore);
    libraryStore.attach(authStore.apiClientProvider);
    rankingsStore.attach(authStore.apiClientProvider);
    actorsStore.attach(authStore.apiClientProvider);
    appNotifications.attach(authStore.snapshotStore);
    appNotifications.setClient(authStore.apiClientProvider);
  }

  aboutToDisappear(): void {
    appNavigationPathStack = null;
    searchStore.detach();
    libraryStore.detach();
    rankingsStore.detach();
    actorsStore.detach();
    appNotifications.detach();
    appNotifications.reset();
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
        .onClick(() => {
          this.pathStack.pushPath({ name: 'Cache' });
        })
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
        BottomTabs({ pathStack: this.pathStack })
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

/**
 * 底部三 Tab（AC-059/AC-060）：媒体库/排行榜/女优。
 * 各 Tab 页面由 TASK-304/305/306 实现，此处为占位容器。
 * Navigation 组合根由 TASK-303 统一拥有。
 */

import { LibraryPage } from '../features/library/LibraryPage';
import { RankingsPage } from '../features/rankings/RankingsPage';
import { ActorsPage } from '../features/actors/ActorsPage';

@Builder
function LibraryTabPlaceholder(pathStack: NavPathStack) {
  LibraryPage({ pathStack: pathStack })
}

@Builder
function RankingsTabPlaceholder(pathStack: NavPathStack) {
  RankingsPage({ pathStack: pathStack })
}

@Builder
function ActorsTabPlaceholder(pathStack: NavPathStack) {
  ActorsPage({ pathStack: pathStack })
}

@Component
export struct BottomTabs {
  @Require pathStack: NavPathStack;
  @State currentIndex: number = 0;

  @Builder
  tabBuilder(index: number, title: string, icon: string) {
    Column({ space: 2 }) {
      SymbolGlyph($r(icon))
        .fontSize(22)
        .fontColor([this.currentIndex === index ? $r('app.color.primary') : $r('app.color.text_secondary')])
      Text(title)
        .fontSize(10)
        .fontColor(this.currentIndex === index ? $r('app.color.primary') : $r('app.color.text_secondary'))
    }
    .justifyContent(FlexAlign.Center)
    .width('100%')
    .height('100%')
  }

  build() {
    Tabs({ barPosition: BarPosition.End }) {
      TabContent() {
        LibraryTabPlaceholder(this.pathStack)
      }
      .tabBar(this.tabBuilder(0, '媒体库', 'sys.symbol.doc'))
      TabContent() {
        RankingsTabPlaceholder(this.pathStack)
      }
      .tabBar(this.tabBuilder(1, '排行榜', 'sys.symbol.star'))
      TabContent() {
        ActorsTabPlaceholder(this.pathStack)
      }
      .tabBar(this.tabBuilder(2, '女优', 'sys.symbol.person'))
    }
    .barHeight(52)
    .scrollable(false)
    .onChange((index: number) => {
      this.currentIndex = index;
    })
    .backgroundColor($r('app.color.surface'))
  }
}

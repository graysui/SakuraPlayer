/**
 * 底部三 Tab（AC-059/AC-060）：媒体库/排行榜/女优。
 * 各 Tab 页面由 TASK-304/305/306 实现，此处为占位容器。
 * Navigation 组合根由 TASK-303 统一拥有。
 */

import { LibraryPage } from '../features/library/LibraryPage';
import { RankingsPage } from '../features/rankings/RankingsPage';

@Builder
function LibraryTabPlaceholder() {
  LibraryPage()
}

@Builder
function RankingsTabPlaceholder() {
  RankingsPage()
}

@Builder
function ActorsTabPlaceholder() {
  Column({ space: 8 }) {
    SymbolGlyph($r('sys.symbol.person'))
      .fontSize(28)
      .fontColor([$r('app.color.text_secondary')])
    Text('女优')
      .fontSize(14)
      .fontColor($r('app.color.text_secondary'))
  }
  .justifyContent(FlexAlign.Center)
  .width('100%')
  .height('100%')
}

@Component
export struct BottomTabs {
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
        LibraryTabPlaceholder()
      }
      .tabBar(this.tabBuilder(0, '媒体库', 'sys.symbol.doc'))
      TabContent() {
        RankingsTabPlaceholder()
      }
      .tabBar(this.tabBuilder(1, '排行榜', 'sys.symbol.star'))
      TabContent() {
        ActorsTabPlaceholder()
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

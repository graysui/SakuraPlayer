/**
 * 全局搜索面板（AC-065/AC-066）：顶部搜索入口的半模态内容。
 * 结果按 影片/女优/元数据补全 分组；pending 显示等待/正在/失败状态；
 * 点击结果经 Navigation 推入对应详情占位路由（由后续任务填充）。
 */

import { searchStore, SearchStatus } from './SearchStore';
import { ActorSummary, MovieSummary, PendingMetadata } from '../../core/api/ApiModels';

@Component
export struct SearchOverlay {
  @State inputText: string = '';
  private pathStack: NavPathStack | null = null;

  private onInputChange(value: string): void {
    this.inputText = value;
    searchStore.updateQuery(value);
  }

  @Builder
  sectionHeader(title: string) {
    Text(title)
      .fontSize(13)
      .fontWeight(FontWeight.Medium)
      .fontColor($r('app.color.text_secondary'))
      .width('100%')
      .padding({ top: 10, bottom: 6 })
  }

  @Builder
  movieRow(item: MovieSummary) {
    Row({ space: 10 }) {
      Column({ space: 2 }) {
        Text(item.number)
          .fontSize(14)
          .fontWeight(FontWeight.Medium)
          .fontColor($r('app.color.text_primary'))
          .maxLines(1)
        Text(item.title)
          .fontSize(13)
          .fontColor($r('app.color.text_secondary'))
          .maxLines(1)
          .textOverflow({ overflow: TextOverflow.Ellipsis })
      }
      .alignItems(HorizontalAlign.Start)
      .layoutWeight(1)
    }
    .width('100%')
    .padding({ top: 8, bottom: 8 })
    .onClick(() => {
      if (this.pathStack !== null) {
        this.pathStack.pushPath({ name: 'MovieDetail', param: item });
      }
    })
  }

  @Builder
  actorRow(item: ActorSummary) {
    Row({ space: 10 }) {
      Text(item.displayName)
        .fontSize(14)
        .fontColor($r('app.color.text_primary'))
        .layoutWeight(1)
        .maxLines(1)
    }
    .width('100%')
    .padding({ top: 8, bottom: 8 })
    .onClick(() => {
      if (this.pathStack !== null) {
        this.pathStack.pushPath({ name: 'ActorDetail', param: item });
      }
    })
  }

  @Builder
  pendingRow(item: PendingMetadata) {
    Row({ space: 8 }) {
      if (item.state === 'failed') {
        Text('!')
          .fontSize(13)
          .fontColor('#FFFFFF')
          .width(18)
          .height(18)
          .textAlign(TextAlign.Center)
          .backgroundColor('#FF3B30')
          .borderRadius(9)
      } else {
        LoadingProgress()
          .width(16)
          .height(16)
      }
      Text(item.number)
        .fontSize(14)
        .fontWeight(FontWeight.Medium)
        .fontColor($r('app.color.text_primary'))
        .maxLines(1)
        .textOverflow({ overflow: TextOverflow.Ellipsis })
        .layoutWeight(1)
      Text(item.state === 'failed' ? '补全失败' : (item.state === 'running' ? '正在补全' : '等待补全'))
        .fontSize(12)
        .fontColor(item.state === 'failed' ? '#FF3B30' : $r('app.color.text_secondary'))
      Blank()
    }
    .width('100%')
    .padding({ top: 8, bottom: 8 })
    .onClick(() => {
      if (this.pathStack !== null) {
        this.pathStack.pushPath({ name: 'PendingDetail', param: item });
      }
    })
  }

  @Builder
  resultList() {
    if (searchStore.status === SearchStatus.LOADING) {
      Row({ space: 8 }) {
        LoadingProgress()
          .width(18)
          .height(18)
        Text('搜索中…')
          .fontSize(13)
          .fontColor($r('app.color.text_secondary'))
      }
      .width('100%')
      .padding({ top: 20 })
      .justifyContent(FlexAlign.Center)
    } else if (searchStore.status === SearchStatus.FAILED) {
      Text(searchStore.errorCode ?? '搜索失败')
        .fontSize(13)
        .fontColor('#FF3B30')
        .maxLines(2)
        .textOverflow({ overflow: TextOverflow.Ellipsis })
        .padding({ top: 20 })
    } else if (searchStore.status === SearchStatus.READY) {
      List({ space: 0 }) {
        if (searchStore.movies.length > 0) {
          ListItem() { this.sectionHeader('影片') }
          ForEach(searchStore.movies, (item: MovieSummary) => {
            ListItem() { this.movieRow(item) }
          }, (item: MovieSummary) => item.id)
        }
        if (searchStore.actors.length > 0) {
          ListItem() { this.sectionHeader('女优') }
          ForEach(searchStore.actors, (item: ActorSummary) => {
            ListItem() { this.actorRow(item) }
          }, (item: ActorSummary) => item.id)
        }
        if (searchStore.pending.length > 0) {
          ListItem() { this.sectionHeader('元数据补全') }
          ForEach(searchStore.pending, (item: PendingMetadata) => {
            ListItem() { this.pendingRow(item) }
          }, (item: PendingMetadata) => item.movieId)
        }
        if (searchStore.movies.length === 0 && searchStore.actors.length === 0 &&
          searchStore.pending.length === 0) {
          ListItem() {
            Text('无匹配结果')
              .fontSize(13)
              .fontColor($r('app.color.text_secondary'))
              .padding({ top: 20 })
          }
        }
      }
      .width('100%')
      .layoutWeight(1)
    }
  }

  build() {
    Column({ space: 8 }) {
      Row({ space: 8 }) {
        TextInput({ placeholder: '搜索番号 / 标题 / 女优', text: this.inputText })
          .type(InputType.Normal)
          .maxLength(200)
          .layoutWeight(1)
          .onChange((value: string) => this.onInputChange(value))
        Text('取消')
          .fontSize(14)
          .fontColor($r('app.color.primary'))
          .onClick(() => {
            searchStore.clear();
            this.inputText = '';
          })
      }
      .width('100%')

      if (this.inputText.trim().length > 0) {
        this.resultList()
      }
    }
    .padding(16)
    .width('100%')
    .height('100%')
  }
}

@Entry
@Component
struct Index {
  private pathStack: NavPathStack = new NavPathStack();

  @Builder
  pageMap(name: string) {
    if (name === 'Home') {
      Column() {
        Text('SakuraPlayer')
          .fontSize(28)
          .fontWeight(FontWeight.Bold)
        Text('HarmonyOS API 24 基线工程')
          .fontSize(14)
          .fontColor('#99000000')
          .margin({ top: 8 })
      }
      .justifyContent(FlexAlign.Center)
      .width('100%')
      .height('100%')
    }
  }

  build() {
    Navigation(this.pathStack) {
      Column() {
        Text('SakuraPlayer')
          .fontSize(24)
          .fontWeight(FontWeight.Bold)
        Button('进入首页骨架')
          .margin({ top: 16 })
          .onClick(() => {
            this.pathStack.pushPath({ name: 'Home' });
          })
      }
      .justifyContent(FlexAlign.Center)
      .width('100%')
      .height('100%')
    }
    .mode(NavigationMode.Stack)
    .hideTitleBar(true)
    .navDestination(this.pageMap)
  }
}
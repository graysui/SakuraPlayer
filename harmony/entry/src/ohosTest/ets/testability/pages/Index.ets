@Entry
@Component
struct Index {
  build() {
    Column({ space: 10 }) {
      Text('SakuraPlayer ohosTest')
        .fontSize(16)
        .fontColor('#333333')
    }
    .justifyContent(FlexAlign.Center)
    .width('100%')
    .height('100%')
  }
}

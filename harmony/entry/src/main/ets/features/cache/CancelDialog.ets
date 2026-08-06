/**
 * 取消等待二次确认对话框（AC-086/087）。
 * 使用 UIContext.openCustomDialog（返回 dialogId）+ closeCustomDialog(dialogId)，
 * 非 deprecated CustomDialog；barrier 不可关闭（唯一出口是等待页的取消按钮）。
 */

import { ComponentContent } from '@kit.ArkUI';

/** CancelDialog 构造参数（class 以满足 ComponentContent 的 T extends Object 约束）。 */
export class CancelDialogParams {
  readonly onCancel: (confirmed: boolean) => void;

  constructor(onCancel: (confirmed: boolean) => void) {
    this.onCancel = onCancel;
  }
}

/** 二次确认对话框内容（openCustomDialog 挂载）。 */
@Builder
export function CancelDialogBuilder(params: CancelDialogParams) {
  Column({ space: 12 }) {
    Text('取消缓存任务？')
      .fontSize(17)
      .fontWeight(FontWeight.Bold)
      .fontColor($r('app.color.text_primary'))
    Text('取消后需要重新选择来源')
      .fontSize(13)
      .fontColor($r('app.color.text_secondary'))
      .textAlign(TextAlign.Center)
      .width('100%')
    Row({ space: 10 }) {
      Button('返回等待')
        .fontSize(14)
        .layoutWeight(1)
        .backgroundColor($r('app.color.surface_alt'))
        .fontColor($r('app.color.text_primary'))
        .onClick(() => {
          params.onCancel(false);
        })
      Button('确认取消')
        .fontSize(14)
        .layoutWeight(1)
        .backgroundColor('#FF3B30')
        .fontColor('#FFFFFF')
        .onClick(() => {
          params.onCancel(true);
        })
    }
    .width('100%')
  }
  .padding(20)
  .width('100%')
  .backgroundColor($r('app.color.background'))
  .borderRadius(16)
}

/** 打开取消确认对话框。onResult(true) 表示用户确认取消。 */
export function openCancelDialog(uiContext: UIContext,
  onResult: (confirmed: boolean) => void): ComponentContent<CancelDialogParams> | null {
  const params = new CancelDialogParams((confirmed: boolean): void => {
    // 先关闭对话框再回调（避免取消失败时对话框残留）
    uiContext.getPromptAction().closeCustomDialog(content).catch(() => {
      // 已关闭则忽略
    });
    onResult(confirmed);
  });
  const content: ComponentContent<CancelDialogParams> =
    new ComponentContent(uiContext, wrapBuilder(CancelDialogBuilder), params);
  uiContext.getPromptAction().openCustomDialog(content, {
    autoCancel: false,
  }).catch(() => {
    // 对话框打开失败：保持等待页可用
  });
  return content;
}

/** 关闭并释放取消对话框（content 版 closeCustomDialog）。 */
export function closeCancelDialog(uiContext: UIContext,
  content: ComponentContent<CancelDialogParams> | null): void {
  if (content === null) {
    return;
  }
  uiContext.getPromptAction().closeCustomDialog(content).catch(() => {
    // 已关闭则忽略
  });
  content.dispose();
}

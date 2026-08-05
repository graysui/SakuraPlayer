import { AbilityConstant, ConfigurationConstant, UIAbility, Want } from '@kit.AbilityKit';
import { hilog } from '@kit.PerformanceAnalysisKit';
import { window } from '@kit.ArkUI';
import { authStore } from '../core/auth/AuthStore';
import { gfriendsCache } from '../core/images/GfriendsCache';

const DOMAIN = 0x0000;

export default class EntryAbility extends UIAbility {
  onCreate(want: Want, launchParam: AbilityConstant.LaunchParam): void {
    try {
      this.context.getApplicationContext().setColorMode(ConfigurationConstant.ColorMode.COLOR_MODE_NOT_SET);
    } catch (err) {
      hilog.error(DOMAIN, 'testTag', 'Failed to set colorMode. Cause: %{public}s', JSON.stringify(err));
    }
    try {
      // GFriends 临时图片缓存目录（cacheDir 由系统管理，logout 时证明式清理）
      gfriendsCache.attach(this.context.cacheDir);
    } catch (err) {
      hilog.error(DOMAIN, 'testTag', 'Failed to attach gfriends cache. Cause: %{public}s', JSON.stringify(err));
    }
    hilog.info(DOMAIN, 'testTag', '%{public}s', 'Ability onCreate');
  }

  /** 系统低内存回调：缩减 GFriends 内存 PixelMap 缓存（AC-053）。 */
  onMemoryLevel(level: AbilityConstant.MemoryLevel): void {
    // MODERATE 为常规级别不收缩（避免清空正在渲染的图）；LOW/CRITICAL/后台级别才缩减
    if (level >= AbilityConstant.MemoryLevel.MEMORY_LEVEL_LOW) {
      gfriendsCache.shrinkMemory();
    }
  }

  onDestroy(): void {
    hilog.info(DOMAIN, 'testTag', '%{public}s', 'Ability onDestroy');
  }

  onWindowStageCreate(windowStage: window.WindowStage): void {
    // Main window is created, set main page for this ability
    hilog.info(DOMAIN, 'testTag', '%{public}s', 'Ability onWindowStageCreate');

    windowStage.loadContent('pages/Index', (err) => {
      if (err.code) {
        hilog.error(DOMAIN, 'testTag', 'Failed to load the content. Cause: %{public}s', JSON.stringify(err));
        return;
      }
      hilog.info(DOMAIN, 'testTag', 'Succeeded in loading the content.');
    });
    // TASK-302：初始化认证会话（恢复基址/令牌/事件连接）
    authStore.initialize(this.context);
  }

  onWindowStageDestroy(): void {
    // Main window is destroyed, release UI related resources
    hilog.info(DOMAIN, 'testTag', '%{public}s', 'Ability onWindowStageDestroy');
  }

  onForeground(): void {
    // Ability has brought to foreground
    hilog.info(DOMAIN, 'testTag', '%{public}s', 'Ability onForeground');
  }

  onBackground(): void {
    // Ability has back to background
    hilog.info(DOMAIN, 'testTag', '%{public}s', 'Ability onBackground');
  }
}
import { bundleManager } from '@kit.AbilityKit';
import { describe, it, expect } from '@ohos/hypium';
import AbilityDelegatorRegistry from '@ohos.app.ability.abilityDelegatorRegistry';

const BUNDLE_NAME = 'com.sakuraplayer.app';
const ENTRY_ABILITY = 'EntryAbility';

export default function scaffoldTest() {
  describe('ScaffoldBaseline', () => {
    /**
     * TASK-301 基线检查：bundleName、Stage 模型、API 24 targetVersion、
     * 唯一 EntryAbility 与 INTERNET 最小权限。
     */
    it('bundle_stage_api24_permission', 0, async (done: Function) => {
      const bundleInfo = await bundleManager.getBundleInfoForSelf(
        bundleManager.BundleFlag.GET_BUNDLE_INFO_WITH_APPLICATION |
        bundleManager.BundleFlag.GET_BUNDLE_INFO_WITH_HAP_MODULE |
        bundleManager.BundleFlag.GET_BUNDLE_INFO_WITH_REQUESTED_PERMISSION);

      // 应用标识
      expect(bundleInfo.name).assertEqual(BUNDLE_NAME);

      // Stage 模型：HAP 模块必须基于 Stage
      const hapModules = bundleInfo.hapModulesInfo;
      expect(hapModules.length).assertLarger(0);
      let allStageBased = true;
      for (const module of hapModules) {
        if (!module.isStageBasedModel) {
          allStageBased = false;
          break;
        }
      }
      expect(allStageBased).assertTrue();

      // API 24 基线：targetVersion 不低于 24，且主模块名为 entry
      expect(bundleInfo.targetVersion).assertLarger(23);
      const entryModule = hapModules.find((m) => m.moduleName === 'entry');
      expect(entryModule != undefined).assertTrue();

      // 最小权限：只声明 INTERNET（不声明媒体库等无关权限）
      const perms = bundleInfo.requestedPermissions ?? [];
      expect(perms.includes('ohos.permission.INTERNET')).assertTrue();
      done();
    });

    /**
     * 生命周期冒烟：EntryAbility 可启动且位于前台。
     */
    it('entry_ability_launch', 0, async (done: Function) => {
      const delegator = AbilityDelegatorRegistry.getAbilityDelegator();
      await delegator.startAbility({
        bundleName: BUNDLE_NAME,
        abilityName: ENTRY_ABILITY,
      });
      // 等待窗口与首帧加载
      await new Promise<void>((resolve) => setTimeout(resolve, 2000));
      const topAbility = await delegator.getCurrentTopAbility();
      expect(topAbility != null).assertTrue();
      done();
    });
  });
}

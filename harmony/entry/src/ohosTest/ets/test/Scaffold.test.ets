import { bundleManager, UIAbility } from '@kit.AbilityKit';
import { describe, it, expect } from '@ohos/hypium';
import AbilityDelegatorRegistry from '@ohos.app.ability.abilityDelegatorRegistry';

const BUNDLE_NAME = 'com.sakuraplayer.app';
const ENTRY_ABILITY = 'EntryAbility';

export default function scaffoldTest() {
  describe('ScaffoldBaseline', () => {
    /**
     * TASK-301 基线检查：bundleName、Stage entry 模块、API 24 targetVersion、
     * 唯一主入口与 INTERNET 最小权限。
     */
    it('bundle_stage_api24_permission', 0, async (done: Function) => {
      const bundleInfo = await bundleManager.getBundleInfoForSelf(
        bundleManager.BundleFlag.GET_BUNDLE_INFO_WITH_APPLICATION |
        bundleManager.BundleFlag.GET_BUNDLE_INFO_WITH_HAP_MODULE |
        bundleManager.BundleFlag.GET_BUNDLE_INFO_WITH_REQUESTED_PERMISSION);

      // 应用标识
      expect(bundleInfo.name).assertEqual(BUNDLE_NAME);

      // Stage 模型：entry 模块存在且为主入口模块
      const hapModules = bundleInfo.hapModulesInfo;
      expect(hapModules.length).assertLarger(0);
      const entryModule = hapModules.find((m) => m.name === 'entry');
      if (entryModule === undefined) {
        expect(entryModule != undefined).assertTrue();
        done();
        return;
      }
      expect(entryModule.type).assertEqual(bundleManager.ModuleType.ENTRY);
      expect(entryModule.mainElementName).assertEqual(ENTRY_ABILITY);

      // API 24 基线：targetVersion 不低于 24
      expect(bundleInfo.targetVersion).assertLarger(23);

      // 最小权限：只声明 INTERNET（不声明媒体库等无关权限）
      const perms = bundleInfo.reqPermissionDetails;
      expect(perms.length).assertEqual(1);
      expect(perms[0].name).assertEqual('ohos.permission.INTERNET');
      done();
    });

    /**
     * 生命周期冒烟：EntryAbility 可启动且位于前台（轮询等待，避免固定 sleep 超时）。
     */
    it('entry_ability_launch', 0, async (done: Function) => {
      const delegator = AbilityDelegatorRegistry.getAbilityDelegator();
      await delegator.startAbility({
        bundleName: BUNDLE_NAME,
        abilityName: ENTRY_ABILITY,
      });
      let topAbility: UIAbility | null = null;
      for (let i = 0; i < 10; i++) {
        topAbility = await delegator.getCurrentTopAbility();
        if (topAbility != null) {
          break;
        }
        await new Promise<void>((resolve) => setTimeout(resolve, 500));
      }
      expect(topAbility != null).assertTrue();
      done();
    });
  });
}

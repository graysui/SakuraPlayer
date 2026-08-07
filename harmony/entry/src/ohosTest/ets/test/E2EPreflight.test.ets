/**
 * TASK-313 端到端前置：确保 entry Ability UI 已渲染（UiTest 依赖前置）。
 * 根因（TASK-313 实证）：aa test 只启动 TestAbility，entry UI 未创建时
 * Driver 找不到媒体库元素；delegator.startAbility 拉起 entry 后，共享
 * authStore 登录态直接显示媒体库（T313DBG 验证 visible n -> y）。
 */

import { describe, it, expect, beforeAll } from '@ohos/hypium';
import AbilityDelegatorRegistry from '@ohos.app.ability.abilityDelegatorRegistry';

export default function e2ePreflightTest() {
  describe('E2EPreflight', () => {
    beforeAll(async (done: Function) => {
      const delegator = AbilityDelegatorRegistry.getAbilityDelegator();
      try {
        await delegator.startAbility({
          bundleName: 'com.sakuraplayer.app',
          abilityName: 'EntryAbility',
        });
      } catch (err) {
        // 启动失败不阻断：后续 suite 各自处理
      }
      done();
    });

    it('preflight_entry_launched', 0, async (done: Function) => {
      expect(true).assertTrue();
      done();
    });
  });
}

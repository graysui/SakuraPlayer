import { abilityDelegatorRegistry, TestRunner } from '@kit.TestKit';
import { UIAbility, Want } from '@kit.AbilityKit';
import { BusinessError } from '@kit.BasicServicesKit';
import { hilog } from '@kit.PerformanceAnalysisKit';

let abilityDelegator: abilityDelegatorRegistry.AbilityDelegator | undefined = undefined;
let abilityDelegatorArguments: abilityDelegatorRegistry.AbilityDelegatorArgs | undefined = undefined;

async function onAbilityCreateCallback(data: UIAbility): Promise<void> {
  hilog.info(0x0000, 'testTag', 'onAbilityCreateCallback, data: %{public}s', JSON.stringify(data) ?? '');
}

async function addAbilityMonitorCallback(err: BusinessError): Promise<void> {
  hilog.info(0x0000, 'testTag', 'addAbilityMonitorCallback : %{public}s', JSON.stringify(err) ?? '');
}

export default class OpenHarmonyTestRunner implements TestRunner {
  constructor() {
  }

  onPrepare(): void {
    hilog.info(0x0000, 'testTag', '%{public}s', 'OpenHarmonyTestRunner OnPrepare');
  }

  async onRun(): Promise<void> {
    hilog.info(0x0000, 'testTag', '%{public}s', 'OpenHarmonyTestRunner onRun run');
    abilityDelegatorArguments = abilityDelegatorRegistry.getArguments();
    abilityDelegator = abilityDelegatorRegistry.getAbilityDelegator();
    const args = abilityDelegatorArguments;
    const moduleName = args.parameters['-m'] ?? '';
    const bundleName = args.bundleName;
    const testAbilityName: string = 'TestAbility';
    const monitor: abilityDelegatorRegistry.AbilityMonitor = {
      abilityName: testAbilityName,
      onAbilityCreate: onAbilityCreateCallback,
      moduleName: moduleName,
    };
    abilityDelegator.addAbilityMonitor(monitor, addAbilityMonitorCallback);
    const want: Want = {
      bundleName: bundleName,
      abilityName: testAbilityName,
      moduleName: moduleName,
    };
    abilityDelegator.startAbility(want, (err: BusinessError) => {
      hilog.info(0x0000, 'testTag', 'startAbility : err : %{public}s', JSON.stringify(err) ?? '');
    });
    hilog.info(0x0000, 'testTag', '%{public}s', 'OpenHarmonyTestRunner onRun end');
  }
}

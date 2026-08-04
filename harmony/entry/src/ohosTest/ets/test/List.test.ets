import abilityTest from './Ability.test';
import scaffoldTest from './Scaffold.test';
import apiClientTest from './ApiClient.test';
import eventClientTest from './EventClient.test';
import appNavigationTest from './AppNavigation.test';

export default function testsuite() {
  abilityTest();
  scaffoldTest();
  apiClientTest();
  eventClientTest();
  appNavigationTest();
}
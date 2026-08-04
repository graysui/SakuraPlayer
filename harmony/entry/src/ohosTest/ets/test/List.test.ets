import abilityTest from './Ability.test';
import scaffoldTest from './Scaffold.test';
import apiClientTest from './ApiClient.test';
import eventClientTest from './EventClient.test';

export default function testsuite() {
  abilityTest();
  scaffoldTest();
  apiClientTest();
  eventClientTest();
}
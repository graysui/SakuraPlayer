import abilityTest from './Ability.test';
import scaffoldTest from './Scaffold.test';
import apiClientTest from './ApiClient.test';
import eventClientTest from './EventClient.test';
import appNavigationTest from './AppNavigation.test';
import libraryStoreTest from './LibraryStore.test';
import libraryPageTest from './LibraryPage.test';

export default function testsuite() {
  abilityTest();
  scaffoldTest();
  apiClientTest();
  eventClientTest();
  appNavigationTest();
  libraryStoreTest();
  libraryPageTest();
}
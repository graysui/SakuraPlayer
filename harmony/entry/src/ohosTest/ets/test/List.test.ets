import abilityTest from './Ability.test';
import scaffoldTest from './Scaffold.test';
import apiClientTest from './ApiClient.test';
import eventClientTest from './EventClient.test';
import appNavigationTest from './AppNavigation.test';
import libraryStoreTest from './LibraryStore.test';
import libraryPageTest from './LibraryPage.test';
import rankingsStoreTest from './RankingsStore.test';
import rankingsPageTest from './RankingsPage.test';
import actorsTest from './Actors.test';
import gfriendsCacheTest from './GfriendsCache.test';
import actorsPageTest from './ActorsPage.test';

export default function testsuite() {
  abilityTest();
  scaffoldTest();
  apiClientTest();
  eventClientTest();
  appNavigationTest();
  libraryStoreTest();
  libraryPageTest();
  rankingsStoreTest();
  rankingsPageTest();
  actorsTest();
  gfriendsCacheTest();
  actorsPageTest();
}
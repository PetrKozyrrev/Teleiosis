import { Platform } from 'react-native';
import { File, Paths } from 'expo-file-system';
import { clearSharedPayloads } from 'expo-sharing';
import { clearDeletedAccount } from '../offline/store';
import { nativeStorage } from '../offline/native';

export async function clearDeletedData(owner: string) {
  await clearDeletedAccount(owner);
  if (Platform.OS === 'ios') {
    const inbox = nativeStorage();
    for (const item of await inbox.pendingShares()) await inbox.removeShare(item.id);
  } else {
    clearSharedPayloads();
  }
  const file = new File(Paths.cache, 'teleiosis-export.json');
  if (file.exists) file.delete();
}

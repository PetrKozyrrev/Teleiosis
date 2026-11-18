import { addNetworkStateListener, getNetworkStateAsync } from 'expo-network';
import { useEffect } from 'react';
import { AppState, Platform } from 'react-native';
import { useAuth } from '../auth/context';
import { API_ORIGIN } from '../auth/config';
import { inspectShare } from '../platform/share';
import { dispatch } from './dispatch';
import { nativeStorage } from './native';
import { claim, importDraft, ownerKey, settle, subscribe } from './store';

let sending = false;

export function OfflineSync() {
  const { controller } = useAuth();
  useEffect(() => {
    let stopped = false;
    let active = AppState.currentState !== 'background' && AppState.currentState !== 'inactive';
    let connected = true;
    let wakeAfterSending = false;
    let lastProbe = 0;

    async function sendQueued() {
      if (!API_ORIGIN || stopped || !active || !connected) return;
      if (sending) {
        wakeAfterSending = true;
        return;
      }
      sending = true;
      try {
        while (!stopped && active && connected) {
          const auth = controller.snapshot();
          const id = auth.session?.user.id;
          if (!id || auth.phase !== 'signedIn' || auth.busy) break;
          const job = await claim(ownerKey(API_ORIGIN, id), Date.now());
          if (!job) break;
          const outcome = await dispatch(job, id, controller.library, Date.now());
          await settle(job, outcome.state, outcome.reason, outcome.nextAt, outcome.serverId, outcome.material);
          if (outcome.state === 'needs_auth' || outcome.reason === 'gateway' || outcome.reason === 'unavailable' ||
              outcome.state === 'retry_wait') {
            wakeAfterSending = false;
            break;
          }
        }
      } catch { /* The next foreground tick can retry local I/O. */ }
      finally {
        sending = false;
        if (wakeAfterSending && !stopped) {
          wakeAfterSending = false;
          void sendQueued();
        }
      }
    }

    async function readInbox() {
      if (Platform.OS !== 'ios' || controller.snapshot().busy) return;
      try {
        const inbox = nativeStorage();
        for (const entry of await inbox.pendingShares()) {
          if (controller.snapshot().busy) return;
          const result = inspectShare([{ shareType: 'text', value: entry.value }]);
          if (result.ok) {
            await importDraft(result.item.kind === 'url' ? { url: result.item.value } : { note: result.item.value }, entry.id);
          }
          await inbox.removeShare(entry.id);
        }
      } catch { /* Leave the native inbox intact for the next foreground transition. */ }
    }

    const start = () => {
      lastProbe = Date.now();
      void readInbox();
      void controller.refresh().catch(() => {}).finally(() => { void sendQueued(); });
    };
    const appState = AppState.addEventListener('change', state => {
      active = state === 'active';
      if (active) start();
    });
    const network = addNetworkStateListener(state => {
      const wasConnected = connected;
      connected = state.isConnected !== false;
      if (connected && !wasConnected && active) start();
    });
    void getNetworkStateAsync().then(state => {
      if (!stopped) connected = state.isConnected !== false;
    }).catch(() => {});
    const unsubscribeAuth = controller.subscribe(() => { void sendQueued(); });
    const unsubscribeStore = subscribe(() => { void sendQueued(); });
    const tick = setInterval(() => {
      if (active && connected && controller.snapshot().phase === 'offline' && Date.now() - lastProbe >= 20_000) start();
      else void sendQueued();
    }, 3_000);
    if (active) start();
    return () => {
      stopped = true;
      clearInterval(tick);
      appState.remove();
      network.remove();
      unsubscribeAuth();
      unsubscribeStore();
    };
  }, [controller]);
  return null;
}

import { createContext, useContext, useEffect, useState, useSyncExternalStore, type PropsWithChildren } from 'react';
import { AppState } from 'react-native';
import { AuthApi } from './api';
import { API_ORIGIN, STAGING_GATE } from './config';
import { AuthController } from './controller';
import { vault } from './vault';
import { resetLearningVisit } from '../learning/events';

const Context = createContext<AuthController | null>(null);

export function AuthProvider({ children }: PropsWithChildren) {
  const [controller] = useState(() => new AuthController(new AuthApi(API_ORIGIN, () => STAGING_GATE && API_ORIGIN ? vault.gateway(API_ORIGIN) : Promise.resolve(null)), vault));
  useEffect(() => {
    const unsubscribe = controller.subscribe(() => {
      if (controller.snapshot().phase === 'signedOut') resetLearningVisit();
    });
    void controller.initialize().catch(() => {});
    const listener = AppState.addEventListener('change', value => {
      if (value === 'active') void controller.refresh().catch(() => {});
    });
    return () => { listener.remove(); unsubscribe(); resetLearningVisit(); };
  }, [controller]);
  return <Context.Provider value={controller}>{children}</Context.Provider>;
}

export function useAuth() {
  const controller = useContext(Context);
  if (!controller) throw new Error('AuthProvider is missing');
  const state = useSyncExternalStore(controller.subscribe, controller.snapshot, controller.snapshot);
  return { controller, state };
}

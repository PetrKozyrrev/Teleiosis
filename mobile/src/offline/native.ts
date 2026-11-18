import { requireNativeModule } from 'expo-modules-core';

export type Incoming = { id: string; value: string };

export function nativeStorage() {
  return requireNativeModule<{
    databaseDirectory(): Promise<string>;
    pendingShares(): Promise<Incoming[]>;
    removeShare(id: string): Promise<void>;
  }>('TeleiosisStorage');
}

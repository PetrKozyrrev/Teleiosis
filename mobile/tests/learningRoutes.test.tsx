import { expect, jest, test } from '@jest/globals';
import { Stack } from 'expo-router';
import { renderRouter, testRouter } from 'expo-router/testing-library';
import TabsLayout from '../src/app/(tabs)/_layout';

jest.mock('../src/auth/context', () => ({
  useAuth: () => ({ state: { phase: 'signedIn', session: { user: { id: 1 } } } }),
}));

test('the app root and existing deep links resolve through the real tab layout', async () => {
  const placeholder = () => null;
  const view = await renderRouter({
    _layout: () => <Stack screenOptions={{ headerShown: false }} />,
    '(tabs)/_layout': TabsLayout,
    '(tabs)/index': placeholder,
    '(tabs)/library': placeholder,
    '(tabs)/goals': placeholder,
    'add-link': placeholder,
    'progress': placeholder,
    '(tabs)/settings': placeholder,
    'library/[id]': placeholder,
    'library/complete': placeholder,
    'library/goals': placeholder,
    'goals/[id]': placeholder,
    'share-probe': placeholder,
  }, { initialUrl: '/' });
  expect(view.getSegments()).toEqual(['(tabs)']);
  await testRouter.navigate('/library');
  await testRouter.push('/library/42');
  expect(view.getSegments()).toEqual(['library', '[id]']);
  await testRouter.push('/library/complete?id=42&taskId=7');
  await testRouter.push('/library/goals?id=42');
  await testRouter.push('/share-probe');
  await testRouter.navigate('/add-link');
  await testRouter.navigate('/progress');
  await testRouter.navigate('/settings');
  await testRouter.navigate('/goals');
  await testRouter.push('/goals/23');
  await testRouter.navigate('/');
  expect(view.getSegments()).toEqual(['(tabs)']);
});

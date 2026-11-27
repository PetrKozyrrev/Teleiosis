import { expect, jest, test } from '@jest/globals';
import { Stack } from 'expo-router';
import { renderRouter, testRouter } from 'expo-router/testing-library';
import TabsLayout from '../src/app/(tabs)/_layout';
import GoalMaterialsRoute from '../src/app/goals/materials';
import TimeBudgetRoute from '../src/app/time-budget';
import type { Request } from '../src/library/model';

jest.mock('../src/auth/context', () => ({
  useAuth: () => ({ state: { phase: 'signedIn', session: { user: { id: 1 } } } }),
}));
jest.mock('../src/library/ui', () => ({
  ...jest.requireActual<typeof import('../src/library/ui')>('../src/library/ui'),
  LibraryAccess: ({ children }: { children: (request: Request, owner: null) => React.ReactNode }) =>
    children(mockBudgetRequest, null),
}));

const mockBudgetRequest = jest.fn<Request>().mockResolvedValue({
  budget_minutes: 15, local_date: '2026-11-27', items: [], has_unknown_duration: false,
});

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
    'time-budget': placeholder,
    '(tabs)/settings': placeholder,
    'library/[id]': placeholder,
    'library/complete': placeholder,
    'library/goals': placeholder,
    'goals/[id]': placeholder,
    'goals/materials': GoalMaterialsRoute,
    'share-probe': placeholder,
  }, { initialUrl: '/' });
  expect(view.getSegments()).toEqual(['(tabs)']);
  await testRouter.push('/time-budget');
  await testRouter.back('/');
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
  await testRouter.push('/goals/materials?goalId=23');
  expect(view.getSegments()).toEqual(['goals', 'materials']);
  expect(mockBudgetRequest.mock.calls).toContainEqual([
    '/mobile/learning/goals/23/candidates?limit=20&offset=0&q=', 'GET',
  ]);
  await testRouter.back('/goals/23');
  await testRouter.navigate('/');
  expect(view.getSegments()).toEqual(['(tabs)']);
});

test('the real budget route loads a supported preset and ignores an unsupported parameter', async () => {
  await renderRouter({
    _layout: () => <Stack screenOptions={{ headerShown: false }} />,
    index: () => null,
    'time-budget': TimeBudgetRoute,
  }, { initialUrl: '/' });
  await testRouter.push('/time-budget?minutes=15');
  expect(mockBudgetRequest.mock.calls).toContainEqual(['/mobile/learning/time-budget?budget_minutes=15', 'GET']);
  await testRouter.back('/');
  mockBudgetRequest.mockClear();
  await testRouter.push('/time-budget?minutes=6');
  expect(mockBudgetRequest).not.toHaveBeenCalled();
  await testRouter.back('/');
});

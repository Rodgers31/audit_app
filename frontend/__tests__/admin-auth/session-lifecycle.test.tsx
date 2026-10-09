import { act, render, screen, waitFor } from '@testing-library/react';
import { AuthProvider, useAuth } from '@/lib/auth/AuthProvider';

const actorA = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
const actorB = 'ffffffff-bbbb-4ccc-8ddd-eeeeeeeeeeee';
const mockGetSession = jest.fn();
const mockGetUser = jest.fn();
const mockProfile = jest.fn();
const mockSignIn = jest.fn();
const mockSignUp = jest.fn();
const mockSignOut = jest.fn();
const mockInsert = jest.fn();
const mockUnsubscribe = jest.fn();
let mockSubscriber: (event: string, session: any) => unknown;
let current: ReturnType<typeof useAuth>;

jest.mock('@/lib/supabase/client', () => ({
  createClient: () => ({
    auth: {
      getSession: (...args: unknown[]) => mockGetSession(...args),
      getUser: (...args: unknown[]) => mockGetUser(...args),
      signInWithPassword: (...args: unknown[]) => mockSignIn(...args),
      signUp: (...args: unknown[]) => mockSignUp(...args),
      signOut: (...args: unknown[]) => mockSignOut(...args),
      onAuthStateChange: (callback: typeof mockSubscriber) => {
        mockSubscriber = callback;
        return { data: { subscription: { unsubscribe: () => mockUnsubscribe() } } };
      },
    },
    from: () => {
      let id: string;
      const query = {
        select: () => query,
        eq: (_column: string, value: string) => { id = value; return query; },
        maybeSingle: () => mockProfile(id),
        insert: (...args: unknown[]) => mockInsert(...args),
      };
      return query;
    },
  }),
}));

function profile(id: string) {
  return { id, email: `${id}@example.test`, display_name: null, roles: ['admin'] };
}
function session(id: string) { return { user: { id, email: `${id}@example.test` } }; }
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function Probe() {
  current = useAuth();
  return <>
    <span data-testid='loading'>{String(current.isLoading)}</span>
    <span data-testid='identity'>{current.authUser?.id ?? 'signed-out'}</span>
    <span data-testid='profile'>{current.user?.id ?? 'no-profile'}</span>
  </>;
}
function mount() { return render(<AuthProvider><Probe /></AuthProvider>); }
async function emit(id: string | null, event = id ? 'SIGNED_IN' : 'SIGNED_OUT') {
  await act(async () => { await mockSubscriber(event, id ? session(id) : null); });
}
beforeEach(() => {
  jest.resetAllMocks();
  mockGetSession.mockResolvedValue({ data: { session: null }, error: null });
  mockGetUser.mockResolvedValue({ data: { user: null }, error: null });
  mockProfile.mockImplementation(async id => ({ data: profile(id), error: null }));
  mockSignOut.mockResolvedValue({ error: null });
  mockInsert.mockResolvedValue({ error: null });
});

test('auth notification releases its SDK lock before querying the profile', async () => {
  const initial = deferred<any>();
  const unlock = deferred<void>();
  mockGetSession.mockReturnValue(initial.promise);
  let locked = true;
  mockProfile.mockImplementation(async id => {
    // SupabaseClient's profile transport awaits auth.getSession(), which must
    // wait for GoTrue to finish the subscriber notification holding this lock.
    if (locked) await unlock.promise;
    return { data: profile(id), error: null };
  });
  mount();
  let completed = false;
  await act(async () => {
    const notification = Promise.resolve(mockSubscriber('INITIAL_SESSION', session(actorA))).then(() => {
      locked = false;
      unlock.resolve();
      initial.resolve({ data: { session: session(actorA) }, error: null });
    });
    let timeout!: ReturnType<typeof setTimeout>;
    completed = await Promise.race([
      notification.then(() => true),
      new Promise<boolean>(resolve => { timeout = setTimeout(() => resolve(false), 60); }),
    ]);
    clearTimeout(timeout);
    if (!completed) {
      // Release only for test cleanup after recording the observable deadlock.
      locked = false; unlock.resolve();
      await notification;
    }
  });
  if (!completed) throw new Error('Auth notification could not release its SDK lock; profile read deadlocked.');
  await waitFor(() => expect(screen.getByTestId('profile')).toHaveTextContent(actorA));
  expect(screen.getByTestId('loading')).toHaveTextContent('false');
});

test('changing identity revokes the previous profile while the next profile is loading', async () => {
  mockGetSession.mockResolvedValue({ data: { session: session(actorA) }, error: null });
  mount();
  await waitFor(() => expect(screen.getByTestId('profile')).toHaveTextContent(actorA));
  const next = deferred<any>();
  mockProfile.mockImplementation(id => id === actorB ? next.promise : Promise.resolve({ data: profile(id), error: null }));
  act(() => { void mockSubscriber('SIGNED_IN', session(actorB)); });
  expect(screen.getByTestId('profile')).toHaveTextContent('no-profile');
  expect(screen.getByTestId('loading')).toHaveTextContent('true');
  await act(async () => { next.resolve({ data: profile(actorB), error: null }); });
  await waitFor(() => expect(screen.getByTestId('profile')).toHaveTextContent(actorB));
});

test('a delayed initial session cannot replace a newer sign-in event', async () => {
  const initial = deferred<any>(); mockGetSession.mockReturnValue(initial.promise);
  mount(); await emit(actorB);
  await waitFor(() => expect(screen.getByTestId('profile')).toHaveTextContent(actorB));
  await act(async () => { initial.resolve({ data: { session: session(actorA) }, error: null }); });
  expect(screen.getByTestId('identity')).toHaveTextContent(actorB);
  expect(screen.getByTestId('profile')).toHaveTextContent(actorB);
});

test('a delayed initial session cannot resurrect an identity after sign-out', async () => {
  const initial = deferred<any>(); mockGetSession.mockReturnValue(initial.promise);
  mount(); await emit(null);
  await act(async () => { initial.resolve({ data: { session: session(actorA) }, error: null }); });
  expect(screen.getByTestId('identity')).toHaveTextContent('signed-out');
  expect(screen.getByTestId('profile')).toHaveTextContent('no-profile');
  expect(screen.getByTestId('loading')).toHaveTextContent('false');
});

test('late profile completion cannot restore privilege after sign-out', async () => {
  const pending = deferred<any>();
  mockGetSession.mockResolvedValue({ data: { session: session(actorA) }, error: null });
  mockProfile.mockReturnValue(pending.promise);
  mount(); await waitFor(() => expect(mockProfile).toHaveBeenCalled());
  await emit(null);
  await act(async () => { pending.resolve({ data: profile(actorA), error: null }); });
  expect(screen.getByTestId('identity')).toHaveTextContent('signed-out');
  expect(screen.getByTestId('profile')).toHaveTextContent('no-profile');
});

test('a prior profile cannot overwrite the next identity profile', async () => {
  const prior = deferred<any>();
  mockGetSession.mockResolvedValue({ data: { session: session(actorA) }, error: null });
  mockProfile.mockImplementation(id => id === actorA ? prior.promise : Promise.resolve({ data: profile(id), error: null }));
  mount(); await waitFor(() => expect(mockProfile).toHaveBeenCalledWith(actorA));
  await emit(actorB);
  await waitFor(() => expect(screen.getByTestId('profile')).toHaveTextContent(actorB));
  await act(async () => { prior.resolve({ data: profile(actorA), error: null }); });
  expect(screen.getByTestId('profile')).toHaveTextContent(actorB);
});

test('profile lookup failure settles loading without retaining old privilege', async () => {
  mockGetSession.mockResolvedValue({ data: { session: session(actorA) }, error: null });
  mount(); await waitFor(() => expect(screen.getByTestId('profile')).toHaveTextContent(actorA));
  mockProfile.mockRejectedValue(new Error('inert lookup failure'));
  act(() => { void mockSubscriber('TOKEN_REFRESHED', session(actorA)); });
  await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));
  expect(screen.getByTestId('profile')).toHaveTextContent('no-profile');
});

test('initial auth errors settle loading without a profile', async () => {
  mockGetSession.mockResolvedValue({ data: { session: session(actorA) }, error: new Error('inert auth failure') });
  mount(); await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));
  expect(screen.getByTestId('profile')).toHaveTextContent('no-profile');
});

test('unmount unsubscribes and ignores an already pending profile', async () => {
  const pending = deferred<any>();
  mockGetSession.mockResolvedValue({ data: { session: session(actorA) }, error: null });
  mockProfile.mockReturnValue(pending.promise);
  const view = mount(); await waitFor(() => expect(mockProfile).toHaveBeenCalled());
  view.unmount(); expect(mockUnsubscribe).toHaveBeenCalledTimes(1);
  await act(async () => { pending.resolve({ data: profile(actorA), error: null }); });
  expect(screen.queryByTestId('profile')).not.toBeInTheDocument();
});

test('login returns and applies the current profile', async () => {
  mockSignIn.mockImplementation(async () => {
    await mockSubscriber('SIGNED_IN', session(actorA));
    return { data: { user: session(actorA).user }, error: null };
  });
  mount(); await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));
  await act(async () => { expect(await current.login('inert@example.test', 'inert-password')).toEqual(profile(actorA)); });
  expect(screen.getByTestId('profile')).toHaveTextContent(actorA);
});

test('refresh cannot replace a newer auth event', async () => {
  mockGetSession.mockResolvedValue({ data: { session: session(actorA) }, error: null });
  const delayed = deferred<any>(); mockGetUser.mockReturnValue(delayed.promise);
  mount(); await waitFor(() => expect(screen.getByTestId('profile')).toHaveTextContent(actorA));
  let refreshing!: Promise<void>;
  act(() => { refreshing = current.refreshUser(); });
  await emit(actorB); await waitFor(() => expect(screen.getByTestId('profile')).toHaveTextContent(actorB));
  await act(async () => { delayed.resolve({ data: { user: session(actorA).user }, error: null }); await refreshing; });
  expect(screen.getByTestId('profile')).toHaveTextContent(actorB);
});

test('registration retains the citizen fallback without reviving a signed-out session', async () => {
  mockSignUp.mockImplementation(async () => {
    await mockSubscriber('SIGNED_IN', session(actorA));
    return { data: { user: session(actorA).user }, error: null };
  });
  const pending = deferred<any>(); mockProfile.mockReturnValue(pending.promise);
  mount(); await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));
  let registering!: Promise<unknown>;
  act(() => { registering = current.register('inert@example.test', 'inert-password'); });
  await waitFor(() => expect(mockProfile).toHaveBeenCalled());
  await emit(null);
  await act(async () => { pending.resolve({ data: null, error: null }); await registering; });
  expect(screen.getByTestId('identity')).toHaveTextContent('signed-out');
  expect(screen.getByTestId('profile')).toHaveTextContent('no-profile');
});

test('a rejected initial session read settles access verification', async () => {
  mockGetSession.mockRejectedValue(new Error('inert auth transport failure'));
  mount();
  await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));
  expect(screen.getByTestId('identity')).toHaveTextContent('signed-out');
  expect(screen.getByTestId('profile')).toHaveTextContent('no-profile');
});

test.each(['auth', 'profile'])('refresh %s failures settle loading and revoke old profile evidence', async failure => {
  mockGetSession.mockResolvedValue({ data: { session: session(actorA) }, error: null });
  mount(); await waitFor(() => expect(screen.getByTestId('profile')).toHaveTextContent(actorA));
  const error = new Error(`inert ${failure} failure`);
  if (failure === 'auth') mockGetUser.mockResolvedValue({ data: { user: null }, error });
  else {
    mockGetUser.mockResolvedValue({ data: { user: session(actorA).user }, error: null });
    mockProfile.mockRejectedValue(error);
  }
  await act(async () => { await expect(current.refreshUser()).rejects.toBe(error); });
  expect(screen.getByTestId('loading')).toHaveTextContent('false');
  expect(screen.getByTestId('profile')).toHaveTextContent('no-profile');
});

test('a delayed login profile cannot replace a newer signed-in identity', async () => {
  mockSignIn.mockImplementation(async () => {
    await mockSubscriber('SIGNED_IN', session(actorA));
    return { data: { user: session(actorA).user }, error: null };
  });
  const pending = deferred<any>();
  mockProfile.mockImplementation(id => id === actorA ? pending.promise : Promise.resolve({ data: profile(id), error: null }));
  mount(); await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));
  let signingIn!: Promise<unknown>;
  act(() => { signingIn = current.login('inert@example.test', 'inert-password'); });
  await waitFor(() => expect(mockProfile).toHaveBeenCalledWith(actorA));
  await emit(actorB); await waitFor(() => expect(screen.getByTestId('profile')).toHaveTextContent(actorB));
  await act(async () => { pending.resolve({ data: profile(actorA), error: null }); await signingIn; });
  expect(screen.getByTestId('identity')).toHaveTextContent(actorB);
  expect(screen.getByTestId('profile')).toHaveTextContent(actorB);
});

test('logout revokes the profile immediately and its late completion preserves a newer event', async () => {
  mockGetSession.mockResolvedValue({ data: { session: session(actorA) }, error: null });
  const pending = deferred<any>(); mockSignOut.mockReturnValue(pending.promise);
  mount(); await waitFor(() => expect(screen.getByTestId('profile')).toHaveTextContent(actorA));
  let signingOut!: Promise<void>;
  act(() => { signingOut = current.logout(); });
  expect(screen.getByTestId('profile')).toHaveTextContent('no-profile');
  expect(screen.getByTestId('identity')).toHaveTextContent('signed-out');
  await emit(actorB); await waitFor(() => expect(screen.getByTestId('profile')).toHaveTextContent(actorB));
  await act(async () => { pending.resolve({ error: null }); await signingOut; });
  expect(screen.getByTestId('profile')).toHaveTextContent(actorB);
});

test('registration returns and applies the trigger-created citizen profile', async () => {
  const citizen = { ...profile(actorA), roles: ['citizen'] };
  mockProfile.mockResolvedValue({ data: citizen, error: null });
  mockSignUp.mockImplementation(async () => {
    await mockSubscriber('SIGNED_IN', session(actorA));
    return { data: { user: session(actorA).user }, error: null };
  });
  mount(); await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));
  await act(async () => { await expect(current.register('inert@example.test', 'inert-password', 'Reader')).resolves.toEqual(citizen); });
  expect(current.user).toEqual(citizen);
  expect(screen.getByTestId('loading')).toHaveTextContent('false');
  expect(mockInsert).not.toHaveBeenCalled();
  expect(mockSignUp).toHaveBeenCalledWith(expect.objectContaining({ options: expect.objectContaining({ data: { display_name: 'Reader' } }) }));
});

test('registration preserves its citizen fallback when no trigger profile is returned', async () => {
  mockProfile.mockResolvedValue({ data: null, error: null });
  mockSignUp.mockImplementation(async () => {
    await mockSubscriber('SIGNED_IN', session(actorA));
    return { data: { user: session(actorA).user }, error: null };
  });
  mount(); await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));
  const citizen = { ...profile(actorA), display_name: 'Reader', roles: ['citizen'] };
  await act(async () => { await expect(current.register('inert@example.test', 'inert-password', 'Reader')).resolves.toEqual(citizen); });
  expect(current.user).toEqual(citizen);
  expect(screen.getByTestId('loading')).toHaveTextContent('false');
  expect(mockInsert).toHaveBeenCalledWith(citizen);
});

test('a queued profile lookup is cancelled when its provider unmounts', async () => {
  const view = mount();
  await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));
  act(() => {
    void mockSubscriber('TOKEN_REFRESHED', session(actorA));
    view.unmount();
  });
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 10)); });
  expect(mockProfile).not.toHaveBeenCalled();
  expect(mockUnsubscribe).toHaveBeenCalledTimes(1);
});

test('registration applies a fresh profile read after a same-identity refresh', async () => {
  mockSignUp.mockResolvedValue({ data: { user: session(actorA).user }, error: null });
  let available = false;
  mockProfile.mockImplementation(async id => ({ data: available ? profile(id) : null, error: null }));
  mount(); await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));
  let registering!: Promise<unknown>;
  act(() => { registering = current.register('inert@example.test', 'inert-password'); });
  await waitFor(() => expect(screen.getByTestId('identity')).toHaveTextContent(actorA));
  await emit(actorA, 'TOKEN_REFRESHED');
  await waitFor(() => expect(mockProfile).toHaveBeenCalled());
  available = true;
  await act(async () => { await expect(registering).resolves.toEqual(profile(actorA)); });
  expect(screen.getByTestId('profile')).toHaveTextContent(actorA);
  expect(screen.getByTestId('loading')).toHaveTextContent('false');
});

test('an older registration profile cannot overwrite newer same-identity role evidence', async () => {
  mockSignUp.mockResolvedValue({ data: { user: session(actorA).user }, error: null });
  const oldProfile = deferred<any>();
  mockProfile.mockReturnValue(oldProfile.promise);
  mount(); await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));
  let registering!: Promise<unknown>;
  act(() => { registering = current.register('inert@example.test', 'inert-password'); });
  await waitFor(() => expect(mockProfile).toHaveBeenCalledWith(actorA));
  const citizen = { ...profile(actorA), roles: ['citizen'] };
  mockProfile.mockResolvedValue({ data: citizen, error: null });
  await emit(actorA, 'TOKEN_REFRESHED');
  await waitFor(() => expect(current.user).toEqual(citizen));
  await act(async () => { oldProfile.resolve({ data: profile(actorA), error: null }); await registering; });
  expect(current.user).toEqual(citizen);
});

test('registration from a departed identity lifetime cannot restore its profile after that actor signs in again', async () => {
  mockSignUp.mockResolvedValue({ data: { user: session(actorA).user }, error: null });
  const oldProfile = deferred<any>();
  mockProfile.mockReturnValue(oldProfile.promise);
  mount(); await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));
  let registering!: Promise<unknown>;
  act(() => { registering = current.register('inert@example.test', 'inert-password'); });
  await waitFor(() => expect(mockProfile).toHaveBeenCalledWith(actorA));
  await emit(null);
  const citizen = { ...profile(actorA), roles: ['citizen'] };
  mockProfile.mockResolvedValue({ data: citizen, error: null });
  await emit(actorA);
  await waitFor(() => expect(current.user).toEqual(citizen));
  await act(async () => { oldProfile.resolve({ data: profile(actorA), error: null }); await registering; });
  expect(current.user).toEqual(citizen);
});

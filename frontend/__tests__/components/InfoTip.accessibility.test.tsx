import { act, fireEvent, render, screen } from '@testing-library/react';
import InfoTip from '@/components/InfoTip';
import { LangProvider, useLang } from '@/lib/i18n/LangProvider';

// The installed ESM export does not resolve its declarations in our TS configuration.
const { computeAccessibleDescription }: { computeAccessibleDescription: (element: Element) => string } =
  require('dom-accessibility-api');

function ChangeLanguage() {
  const { setLang } = useLang();
  return <>
    <button onClick={() => setLang('sw')}>Swahili</button>
    <button onClick={() => setLang('plain')}>Plain English</button>
    <button onClick={() => setLang('en')}>English</button>
  </>;
}

function focus(button: HTMLElement) {
  act(() => button.focus());
  expect(document.activeElement).toBe(button);
}

function expectDescription(button: HTMLElement, tooltip: HTMLElement) {
  const description = computeAccessibleDescription(button);
  if (description === '') {
    throw new Error(`Open trigger has no computed description: ${JSON.stringify({
      focused: document.activeElement === button,
      tooltipId: tooltip.id,
      describedBy: button.getAttribute('aria-describedby'),
      description,
      content: tooltip.textContent,
    })}`);
  }
  expect(tooltip.id).not.toBe('');
  expect(button).toHaveAttribute('aria-describedby', tooltip.id);
  expect(document.getElementById(tooltip.id)).toBe(tooltip);
  expect(description).toBe(
    Array.from(tooltip.children, child => child.textContent).join(' ').replace(/\s+/g, ' ').trim()
  );
}

function expectClosed(button: HTMLElement) {
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  expect(button).not.toHaveAttribute('aria-describedby');
  expect(computeAccessibleDescription(button)).toBe('');
}

afterEach(() => {
  localStorage.clear();
  jest.useRealTimers();
});

it('positive control: genuine keyboard focus opens populated portal and Escape preserves focus', () => {
  const { container } = render(<LangProvider><InfoTip term='pending-bills' /></LangProvider>);
  const button = screen.getByRole('button', { name: 'What is Pending Bills?' });
  focus(button);
  const tooltip = screen.getByRole('tooltip');
  expect(container).not.toContainElement(tooltip);
  expect(document.body).toContainElement(tooltip);
  expect(tooltip).not.toHaveStyle({ display: 'none' });
  expect(tooltip).toHaveTextContent('Missing information is not zero');
  fireEvent.keyDown(button, { key: 'Escape' });
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  expect(document.activeElement).toBe(button);
});

it('positive control: computed description detects a real reference relationship', () => {
  render(<><button aria-describedby='reference-tip'>Reference help</button>
    <div id='reference-tip' role='tooltip'>Missing information is not zero.</div></>);
  const button = screen.getByRole('button');
  focus(button);
  expect(computeAccessibleDescription(button)).toBe('Missing information is not zero.');
});

it('describes the genuinely focused trigger with its actual portal content', () => {
  render(<LangProvider><InfoTip term='pending-bills' /></LangProvider>);
  const button = screen.getByRole('button', { name: 'What is Pending Bills?' });
  expectClosed(button);
  focus(button);
  const tooltip = screen.getByRole('tooltip');
  expect(tooltip).toHaveTextContent('Missing information is not zero');
  expectDescription(button, tooltip);
  expect(computeAccessibleDescription(button)).toContain('Missing information is not zero');
  expect(button).toHaveAccessibleName('What is Pending Bills?');
});

it.each(['Escape', 'outside', 'click', 'blur', 'hover leave'])(
  'removes the description on %s and retains its identity on repeated reopen', (close) => {
    jest.useFakeTimers();
    render(<InfoTip term='principal' />);
    const button = screen.getByRole('button', { name: 'What is Principal?' });
    let id: string | undefined;
    for (let cycle = 0; cycle < 3; cycle++) {
      act(() => button.blur());
      focus(button);
      const tooltip = screen.getByRole('tooltip');
      expectDescription(button, tooltip);
      if (id !== undefined) expect(tooltip.id).toBe(id);
      id = tooltip.id;
      if (close === 'Escape') fireEvent.keyDown(button, { key: 'Escape' });
      if (close === 'outside') fireEvent.mouseDown(document.body);
      if (close === 'click') fireEvent.click(button);
      if (close === 'blur') act(() => button.blur());
      if (close === 'hover leave') fireEvent.mouseLeave(button);
      if (close === 'blur' || close === 'hover leave') {
        act(() => jest.advanceTimersByTime(149));
        expectDescription(button, tooltip);
        act(() => jest.advanceTimersByTime(1));
      }
      expectClosed(button);
      expect(document.getElementById(id!)).toBeNull();
    }
  }
);

it('keeps same-term and different-term instances unique and independently associated', () => {
  jest.useFakeTimers();
  render(<><InfoTip term='pending-bills' /><InfoTip term='pending-bills' />
    <InfoTip term='principal' /></>);
  const buttons = screen.getAllByRole('button');
  buttons.forEach(button => fireEvent.mouseEnter(button));
  const tooltips = screen.getAllByRole('tooltip');
  expect(new Set(tooltips.map(tooltip => tooltip.id)).size).toBe(3);
  buttons.forEach((button, index) => expectDescription(button, tooltips[index]));
  expect(computeAccessibleDescription(buttons[2])).toContain('original amount borrowed');
  fireEvent.click(buttons[1]);
  expect(buttons[1]).not.toHaveAttribute('aria-describedby');
  expect(document.getElementById(tooltips[1].id)).toBeNull();
  expectDescription(buttons[0], tooltips[0]);
  expectDescription(buttons[2], tooltips[2]);
});

it('updates the open description and question in all languages without changing identity', () => {
  render(<LangProvider><ChangeLanguage /><InfoTip term='pending-bills' /></LangProvider>);
  const button = screen.getByRole('button', { name: 'What is Pending Bills?' });
  focus(button);
  const tooltip = screen.getByRole('tooltip');
  expectDescription(button, tooltip);
  const id = tooltip.id;
  const english = computeAccessibleDescription(button);
  fireEvent.click(screen.getByRole('button', { name: 'Swahili' }));
  expect(button).toHaveAccessibleName('Bili Ambazo Hazijalipwa ni nini?');
  expect(computeAccessibleDescription(button)).toContain('kutopatikana si sawa na sifuri');
  expectDescription(button, tooltip);
  fireEvent.click(screen.getByRole('button', { name: 'Plain English' }));
  expect(button).toHaveAccessibleName('What does Unpaid bills mean?');
  expect(computeAccessibleDescription(button)).toContain('Missing information is not zero');
  expect(computeAccessibleDescription(button)).not.toBe(english);
  expectDescription(button, tooltip);
  fireEvent.click(screen.getByRole('button', { name: 'English' }));
  expect(button).toHaveAccessibleName('What is Pending Bills?');
  expect(computeAccessibleDescription(button)).toBe(english);
  expectDescription(button, tooltip);
  expect(tooltip.id).toBe(id);
});

it.each(['pending-bills', 'principal'])('associates %s without a language provider', (term) => {
  render(<InfoTip term={term} />);
  const button = screen.getByRole('button');
  expectClosed(button);
  focus(button);
  expectDescription(button, screen.getByRole('tooltip'));
});

it.each(['', 'missing-term', ...Object.getOwnPropertyNames(Object.prototype)])(
  'omits unknown or inherited term %s without a tooltip or reference', (term) => {
    const { container } = render(<InfoTip term={term} />);
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
    expect(document.querySelector('[aria-describedby]')).toBeNull();
  }
);

it('removes an open portal when the term becomes unknown or the component unmounts', () => {
  const { rerender, unmount } = render(<InfoTip term='pending-bills' />);
  focus(screen.getByRole('button'));
  const tooltip = screen.getByRole('tooltip');
  expectDescription(screen.getByRole('button'), tooltip);
  const id = tooltip.id;
  rerender(<InfoTip term='constructor' />);
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  expect(document.getElementById(id)).toBeNull();
  expect(document.querySelector('[aria-describedby]')).toBeNull();
  rerender(<InfoTip term='principal' />);
  const replacement = screen.getByRole('button', { name: 'What is Principal?' });
  fireEvent.mouseEnter(replacement);
  expectDescription(replacement, screen.getByRole('tooltip'));
  expect(computeAccessibleDescription(replacement)).toContain('original amount borrowed');
  expect(computeAccessibleDescription(replacement)).not.toContain('pending bills');
  unmount();
  expect(document.getElementById(id)).toBeNull();
  expect(document.querySelector('[aria-describedby]')).toBeNull();
});

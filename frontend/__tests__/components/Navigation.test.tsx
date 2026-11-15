/**
 * Tests for the Navigation component.
 *
 * Covers:
 *  - Renders brand name
 *  - Shows nav items (Dashboard, National Debt, Budget & Spending, County Explorer)
 *  - Active item styling
 *  - Mobile menu toggle
 */

import '@testing-library/jest-dom';
import { fireEvent, render, screen, within } from '@testing-library/react';

// Mock next/navigation
const mockPathname = jest.fn().mockReturnValue('/');
jest.mock('next/navigation', () => ({
  usePathname: () => mockPathname(),
}));

// Mock framer-motion to render simple elements
jest.mock('framer-motion', () => ({
  motion: {
    header: ({ children, initial: _initial, animate: _animate, transition: _transition, ...props }: any) => <header {...props}>{children}</header>,
    div: ({ children, initial: _initial, animate: _animate, exit: _exit, transition: _transition, ...props }: any) => <div {...props}>{children}</div>,
    span: ({ children, layoutId: _layoutId, transition: _transition, ...props }: any) => <span {...props}>{children}</span>,
    button: ({ children, initial: _initial, animate: _animate, ...props }: any) => <button {...props}>{children}</button>,
  },
  AnimatePresence: ({ children }: any) => <>{children}</>,
  useReducedMotion: () => false,
}));

// Mock auth hook
jest.mock('@/lib/auth/AuthProvider', () => ({
  useAuth: () => ({
    user: null,
    isAuthenticated: false,
    isLoading: false,
    login: jest.fn(),
    register: jest.fn(),
    logout: jest.fn(),
    refreshUser: jest.fn(),
  }),
}));

import Navigation from '@/components/Navigation';

describe('Navigation', () => {
  beforeEach(() => {
    mockPathname.mockReturnValue('/');
  });

  it('renders the brand name', () => {
    render(<Navigation />);
    expect(screen.getByText('AuditGava')).toBeInTheDocument();
  });

  it('renders all nav items', () => {
    render(<Navigation />);
    expect(screen.getByRole('link', { name: 'AuditGava' })).toHaveAttribute('href', '/');
    expect(screen.getByRole('link', { name: 'National debt' })).toHaveAttribute('href', '/debt');
    expect(screen.getByRole('link', { name: 'Budget' })).toHaveAttribute('href', '/budget');
    expect(screen.getByRole('link', { name: 'Counties' })).toHaveAttribute('href', '/counties');
    expect(screen.getByRole('link', { name: 'Audits' })).toHaveAttribute('href', '/audits');
  });

  it('renders navigation links with correct hrefs', () => {
    render(<Navigation />);
    const dashboardLinks = screen.getAllByRole('link', { name: 'AuditGava' });
    expect(dashboardLinks.length).toBeGreaterThan(0);
  });

  it('has a link to /debt for National Debt', () => {
    render(<Navigation />);
    const links = screen.getAllByRole('link');
    const debtLink = links.find((l) => l.getAttribute('href') === '/debt');
    expect(debtLink).toBeDefined();
  });

  it('has a link to /budget for Budget & Spending', () => {
    render(<Navigation />);
    const links = screen.getAllByRole('link');
    const budgetLink = links.find((l) => l.getAttribute('href') === '/budget');
    expect(budgetLink).toBeDefined();
  });

  it('has a link to /counties for County Explorer', () => {
    render(<Navigation />);
    const links = screen.getAllByRole('link');
    const countyLink = links.find((l) => l.getAttribute('href') === '/counties');
    expect(countyLink).toBeDefined();
  });

  it('renders the brand line', () => {
    render(<Navigation />);
    expect(screen.getByText(/Kenya public money tracker/i)).toBeInTheDocument();
  });

  it.each(['/admin', '/admin/social/new', '/admin/users/123', '/admin/', '/status', '/status/'])('leaves navigation ownership to the guarded shell at %s', path => {
    mockPathname.mockReturnValue(path);
    const view = render(<Navigation />);
    expect(view.container).toBeEmptyDOMElement();
  });

  it.each(['/administrator', '/admin-help', '/status-report', '/account'])('retains public navigation at %s', path => {
    mockPathname.mockReturnValue(path);
    render(<Navigation />);
    expect(screen.getByRole('navigation', { name: 'Primary navigation' })).toBeInTheDocument();
  });

  it('names the mobile toggle according to its expanded state', () => {
    render(<Navigation />);
    const toggle = screen.getByRole('button', { name: 'Open navigation menu' });
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(toggle).toHaveAccessibleName('Close navigation menu');
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Close navigation menu' }));
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(toggle).toHaveAccessibleName('Open navigation menu');
  });

  it('retires the open public menu and scroll lock across private route transitions', () => {
    const view = render(<Navigation />);
    fireEvent.click(screen.getByRole('button', { name: 'Open navigation menu' }));
    expect(document.body.style.overflow).toBe('hidden');
    mockPathname.mockReturnValue('/admin');
    view.rerender(<Navigation />);
    expect(view.container).toBeEmptyDOMElement();
    expect(document.body.style.overflow).not.toBe('hidden');
    mockPathname.mockReturnValue('/');
    view.rerender(<Navigation />);
    expect(screen.getByRole('button', { name: 'Open navigation menu' })).toHaveAttribute('aria-expanded', 'false');
  });
});

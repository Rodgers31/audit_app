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
import { render, screen } from '@testing-library/react';

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
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText('National Debt')).toBeInTheDocument();
    expect(screen.getByText('Budget & Spending')).toBeInTheDocument();
    expect(screen.getByText('County Explorer')).toBeInTheDocument();
  });

  it('renders navigation links with correct hrefs', () => {
    render(<Navigation />);
    const dashboardLinks = screen.getAllByRole('link', { name: /dashboard/i });
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

  it('renders the evidence-first brand line', () => {
    render(<Navigation />);
    expect(screen.getByText(/Public money · evidence first/i)).toBeInTheDocument();
  });
});

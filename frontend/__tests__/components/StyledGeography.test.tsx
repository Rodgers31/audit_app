import { act, fireEvent, render, screen } from '@testing-library/react';
import { createRef } from 'react';
import StyledGeography from '@/components/map/StyledGeography';

// Geography itself needs no projection. Stub its unused D3 module imports so
// Jest can load the real package's CommonJS entry without executing ESM D3.
jest.mock('d3-geo', () => ({}));
jest.mock('d3-zoom', () => ({}));
jest.mock('d3-selection', () => ({}));

const geography = {
  type: 'Feature' as const,
  geometry: { type: 'Polygon' as const, coordinates: [] },
  properties: { NAME_1: 'Synthetic county' },
  rsmKey: 'synthetic-county',
  svgPath: 'M0,0L20,0L20,20Z',
};

it('preserves county colors through pointer, pressed, focus, and blur states', () => {
  const ref = createRef<SVGPathElement>();
  const handlers = {
    onMouseEnter: jest.fn(), onMouseLeave: jest.fn(), onMouseDown: jest.fn(),
    onMouseUp: jest.fn(), onFocus: jest.fn(), onBlur: jest.fn(),
    onClick: jest.fn(), onKeyDown: jest.fn(),
  };
  render(<svg><StyledGeography geography={geography} ref={ref} role='button'
    aria-label='Synthetic county' aria-expanded={false} tabIndex={0}
    {...handlers} style={{default:{fill:'#c3cdd5'},hover:{fill:'#a9b6c0'},pressed:{fill:'#1B3A2A'}}}/></svg>);
  const county = screen.getByRole('button', {name:'Synthetic county'});
  expect(ref.current).toBe(county);
  expect(county).toHaveAttribute('d', geography.svgPath);
  expect(county).toHaveAttribute('aria-expanded', 'false');
  expect(county).toHaveStyle({fill:'#c3cdd5'});
  fireEvent.mouseEnter(county);
  expect(county).toHaveStyle({fill:'#a9b6c0'});
  fireEvent.mouseDown(county);
  expect(county).toHaveStyle({fill:'#1B3A2A'});
  fireEvent.mouseLeave(county);
  expect(county).toHaveStyle({fill:'#c3cdd5'});
  fireEvent.focus(county);
  expect(county).toHaveStyle({fill:'#a9b6c0'});
  fireEvent.mouseDown(county);
  fireEvent.blur(county);
  expect(county).toHaveStyle({fill:'#c3cdd5'});
  fireEvent.mouseEnter(county);
  fireEvent.mouseDown(county);
  fireEvent.mouseUp(county);
  expect(county).toHaveStyle({fill:'#a9b6c0'});
  fireEvent.click(county);
  fireEvent.keyDown(county, {key:'Enter'});
  for (const handler of Object.values(handlers)) {
    expect(handler).toHaveBeenCalled();
    expect(handler.mock.calls[0][0].target).toBe(county);
  }
  expect(handlers.onMouseEnter).toHaveBeenCalledTimes(2);
  expect(handlers.onMouseDown).toHaveBeenCalledTimes(3);
  for (const name of ['onMouseLeave', 'onMouseUp', 'onFocus', 'onBlur', 'onClick', 'onKeyDown'] as const) {
    expect(handlers[name]).toHaveBeenCalledTimes(1);
  }
});

it('does not invent missing style states or retain default styles on hover', () => {
  render(<svg><StyledGeography geography={geography} aria-label='Synthetic county'
    role='button' style={{default:{fill:'#c3cdd5',stroke:'#3d5a45'}}}/></svg>);
  const county = screen.getByRole('button', {name:'Synthetic county'});
  expect(county).toHaveAttribute('tabindex', '0');
  expect(county).toHaveStyle({fill:'#c3cdd5',stroke:'#3d5a45'});
  fireEvent.mouseEnter(county);
  expect(county.style.fill).toBe('');
  expect(county.style.stroke).toBe('');
  fireEvent.mouseLeave(county);
  expect(county).toHaveStyle({fill:'#c3cdd5',stroke:'#3d5a45'});
});

it('keeps the keyboard focus style when the pointer leaves the focused county', () => {
  render(<svg><StyledGeography geography={geography} aria-label='Synthetic county'
    role='button' style={{default:{fill:'#c3cdd5'},hover:{fill:'#a9b6c0'},pressed:{fill:'#1B3A2A'}}}/></svg>);
  const county = screen.getByRole('button', {name:'Synthetic county'});
  act(() => county.focus());
  expect(county).toHaveFocus();
  fireEvent.mouseEnter(county);
  fireEvent.mouseDown(county);
  expect(county).toHaveStyle({fill:'#1B3A2A'});
  fireEvent.mouseLeave(county);
  expect(county).toHaveFocus();
  expect(county).toHaveStyle({fill:'#a9b6c0'});
  act(() => county.blur());
  expect(county).not.toHaveFocus();
  expect(county).toHaveStyle({fill:'#c3cdd5'});
});

it('keeps the pointer hover style when keyboard focus moves away', () => {
  render(<svg><StyledGeography geography={geography} aria-label='Synthetic county'
    role='button' style={{default:{fill:'#c3cdd5'},hover:{fill:'#a9b6c0'},pressed:{fill:'#1B3A2A'}}}/></svg>);
  const county = screen.getByRole('button', {name:'Synthetic county'});
  fireEvent.mouseEnter(county);
  act(() => county.focus());
  fireEvent.mouseDown(county);
  expect(county).toHaveStyle({fill:'#1B3A2A'});
  act(() => county.blur());
  expect(county).not.toHaveFocus();
  expect(county).toHaveStyle({fill:'#a9b6c0'});
  fireEvent.mouseLeave(county);
  expect(county).toHaveStyle({fill:'#c3cdd5'});
});

it('uses current styles and callbacks after a rerender during interaction', () => {
  const oldLeave = jest.fn();
  const newLeave = jest.fn();
  const newDown = jest.fn();
  const ref = createRef<SVGPathElement>();
  const {rerender} = render(<svg><StyledGeography ref={ref} geography={geography}
    role='button' aria-label='Synthetic county' aria-expanded={false} onMouseLeave={oldLeave}
    style={{default:{fill:'#c3cdd5'},hover:{fill:'#a9b6c0'}}}/></svg>);
  const county = screen.getByRole('button', {name:'Synthetic county'});
  fireEvent.mouseEnter(county);
  act(() => county.focus());
  rerender(<svg><StyledGeography ref={ref} geography={geography} role='button'
    aria-label='Synthetic county' aria-expanded={true} onMouseLeave={newLeave}
    onMouseDown={newDown} style={{default:{fill:'#4A7C5C'},hover:{fill:'#3d6a4e'},pressed:{fill:'#1B3A2A'}}}/></svg>);
  expect(ref.current).toBe(county);
  expect(county).toHaveAttribute('aria-expanded', 'true');
  expect(county).toHaveStyle({fill:'#3d6a4e'});
  fireEvent.mouseDown(county);
  expect(county).toHaveStyle({fill:'#1B3A2A'});
  fireEvent.mouseLeave(county);
  expect(county).toHaveFocus();
  expect(county).toHaveStyle({fill:'#3d6a4e'});
  expect(oldLeave).not.toHaveBeenCalled();
  expect(newLeave).toHaveBeenCalledTimes(1);
  expect(newDown).toHaveBeenCalledTimes(1);
  act(() => county.blur());
  expect(county).toHaveStyle({fill:'#4A7C5C'});
});

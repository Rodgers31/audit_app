'use client';

import { forwardRef, memo, useState, type CSSProperties } from 'react';
import { Geography, type GeographyProps } from 'react-simple-maps';

type GeographyStyles = Partial<Record<'default' | 'hover' | 'pressed', CSSProperties>>;

export interface StyledGeographyProps extends Omit<GeographyProps, 'style'> {
  style?: GeographyStyles;
}

/** v5 accepts plain SVG styles. Preserve the v3 county style states, including
 * keyboard focus, without changing the callers' colors or input handlers. */
const StyledGeography = forwardRef<SVGPathElement, StyledGeographyProps>(
  function StyledGeography(
    {
      style = {},
      onMouseEnter,
      onMouseLeave,
      onMouseDown,
      onMouseUp,
      onFocus,
      onBlur,
      ...props
    },
    ref
  ) {
    const [isPressed, setPressed] = useState(false);
    const [isFocused, setFocused] = useState(false);

    return (
      <Geography
        {...props}
        ref={ref}
        style={style[isPressed ? 'pressed' : isFocused ? 'hover' : 'default']}
        onMouseEnter={(event) => {
          setFocused(true);
          onMouseEnter?.(event);
        }}
        onMouseLeave={(event) => {
          setFocused(false);
          setPressed(false);
          onMouseLeave?.(event);
        }}
        onMouseDown={(event) => {
          setPressed(true);
          onMouseDown?.(event);
        }}
        onMouseUp={(event) => {
          setPressed(false);
          onMouseUp?.(event);
        }}
        onFocus={(event) => {
          setFocused(true);
          onFocus?.(event);
        }}
        onBlur={(event) => {
          setFocused(false);
          setPressed(false);
          onBlur?.(event);
        }}
      />
    );
  }
);

export default memo(StyledGeography);

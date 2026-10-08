'use client';

import { forwardRef, memo, useState, type CSSProperties } from 'react';
import { Geography, type GeographyProps } from 'react-simple-maps';

type GeographyStyles = Partial<Record<'default' | 'hover' | 'pressed', CSSProperties>>;

export interface StyledGeographyProps extends Omit<GeographyProps, 'style'> {
  style?: GeographyStyles;
}

/** v5 accepts plain SVG styles. Keep the county palette's style states while
 * tracking hover and keyboard focus separately, so either can remain visible. */
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
    const [isHovered, setHovered] = useState(false);
    const [isFocused, setFocused] = useState(false);

    return (
      <Geography
        {...props}
        ref={ref}
        style={style[isPressed ? 'pressed' : isHovered || isFocused ? 'hover' : 'default']}
        onMouseEnter={(event) => {
          setHovered(true);
          onMouseEnter?.(event);
        }}
        onMouseLeave={(event) => {
          setHovered(false);
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

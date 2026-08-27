export interface SeatPos {
  /** Horizontal position as a percentage of the table stage width. */
  left: number;
  /** Vertical position as a percentage of the table stage height. */
  top: number;
}

/**
 * Seat positions around an oval table, expressed as percentages of the
 * surrounding stage box (apply with `translate(-50%, -50%)`).
 *
 * Index ordering matches the caller's play-order list; ``viewerIndex`` marks
 * where the local player sits, and is pinned to bottom-center. Everyone else
 * is distributed evenly through the remaining arc **in play order**, so the
 * physical ring preserves turn order. Partnership games seat teammates
 * alternately around the table (A-B-A-B), which this even spacing turns into
 * diametrically-opposite partners for free.
 */
export function seatPositions(count: number, viewerIndex: number): SeatPos[] {
  const out: SeatPos[] = [];
  for (let i = 0; i < count; i++) {
    // Offset in play order measured clockwise from the viewer's seat.
    const offset = (((i - viewerIndex) % count) + count) % count;
    // Screen coords: y grows downward, so 90deg lands at bottom-center and
    // increasing angle walks clockwise as seen on screen.
    const theta = Math.PI / 2 + (offset * 2 * Math.PI) / count;
    const left = 50 + RADIUS_X * Math.cos(theta);
    const top = 50 + RADIUS_Y * Math.sin(theta);
    out.push({ left, top });
  }
  return out;
}

/** Horizontal semi-axis (% of stage width) for seat centers. Kept inside the
 *  stage so tiles never push past the viewport; tiles straddle the felt edge. */
const RADIUS_X = 42;

/** Vertical semi-axis (% of stage height). Kept small enough that the top
 *  tile straddles the felt's top edge instead of clipping the status bar. */
const RADIUS_Y = 37;

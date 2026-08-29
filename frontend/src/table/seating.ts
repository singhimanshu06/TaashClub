export interface SeatPos {
  /** Horizontal position as a percentage of the table stage width. */
  left: number;
  /** Vertical position as a percentage of the table stage height. */
  top: number;
  /** Which rim edge of the table this seat is projected onto. The tile is
   *  anchored OUTSIDE the table with its near edge touching this rim (see
   *  the `.seat-rim-*` translates in styles.css). */
  rim: "top" | "bottom" | "left" | "right";
}

/**
 * Seat positions around the table RIM, expressed as percentages of the
 * surrounding stage box.
 *
 * Angles are spaced equally around an ellipse (viewer pinned bottom-center),
 * which preserves turn order around the table and seats partnership
 * teammates opposite (4p) / alternately (6p). Each seat is then PROJECTED
 * onto the table's rim rectangle (the felt): side seats pin against the
 * left/right rims, top/bottom seats against the top/bottom rims, keeping
 * their along-rim coordinate from the ellipse. Tiles anchor outside the
 * table, near edge touching the rim — the felt surface itself stays clear
 * for the card row. Narrow/short screens straddle instead (see styles.css).
 */
export function seatPositions(count: number, viewerIndex: number): SeatPos[] {
  const out: SeatPos[] = [];
  for (let i = 0; i < count; i++) {
    // Offset in play order measured clockwise from the viewer's seat.
    const offset = (((i - viewerIndex) % count) + count) % count;
    // Screen coords: y grows downward, so 90deg lands at bottom-center and
    // increasing angle walks clockwise as seen on screen.
    const theta = Math.PI / 2 + (offset * 2 * Math.PI) / count;
    const cos = Math.cos(theta);
    const sin = Math.sin(theta);
    if (Math.abs(cos) > Math.abs(sin)) {
      // Nearest the left/right rim: pin horizontally on the rim, keep the
      // ellipse's vertical coordinate (spread along the edge).
      out.push(
        cos > 0
          ? { left: RIM_RIGHT, top: 50 + RADIUS_Y * sin, rim: "right" }
          : { left: RIM_LEFT, top: 50 + RADIUS_Y * sin, rim: "left" }
      );
    } else {
      // Nearest the top/bottom rim: pin vertically on the rim, keep the
      // ellipse's horizontal coordinate (spread along the edge).
      out.push(
        sin > 0
          ? { left: 50 + RADIUS_X * cos, top: RIM_BOTTOM, rim: "bottom" }
          : { left: 50 + RADIUS_X * cos, top: RIM_TOP, rim: "top" }
      );
    }
  }
  return out;
}

/** Horizontal semi-axis of the seat ellipse (% of stage width). Side seats
 *  land on the left/right rims at 50 ± RADIUS_X. Keep the felt's side inset
 *  in styles.css in sync (100 − 2·RADIUS_X = 10% per side). */
const RADIUS_X = 40;

/** Vertical semi-axis of the seat ellipse (% of stage height). Top/bottom
 *  seats land on the rims at 50 ± RADIUS_Y. Kept small enough that the
 *  tiles anchored above the table don't poke into the status bar; keep the
 *  felt's top/bottom inset in sync (100 − 2·RADIUS_Y = 16% per side). */
const RADIUS_Y = 34;

/** Rim rectangle edges (% of the stage box) — mirror of the felt's insets. */
const RIM_LEFT = 50 - RADIUS_X; // 10
const RIM_RIGHT = 50 + RADIUS_X; // 90
const RIM_TOP = 50 - RADIUS_Y; // 16
const RIM_BOTTOM = 50 + RADIUS_Y; // 84

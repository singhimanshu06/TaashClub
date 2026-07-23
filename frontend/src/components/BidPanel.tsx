import { useState } from "react";

interface Props {
  maxBid: number;
  onBid: (value: number) => void;
}

export default function BidPanel({ maxBid, onBid }: Props) {
  const [value, setValue] = useState(0);
  const clamp = (v: number) => Math.max(0, Math.min(maxBid, v));

  return (
    <div className="bid-panel">
      <div className="bid-row">
        <div className="bid-stepper">
          <button
            className="step-btn"
            disabled={value <= 0}
            onClick={() => setValue((v) => clamp(v - 1))}
            aria-label="decrease bid"
          >
            −
          </button>
          <div className="step-value">
            <span className="step-num">{value}</span>
            <small>of {maxBid}</small>
          </div>
          <button
            className="step-btn"
            disabled={value >= maxBid}
            onClick={() => setValue((v) => clamp(v + 1))}
            aria-label="increase bid"
          >
            +
          </button>
        </div>
        <button className="btn-primary bid-confirm" onClick={() => onBid(clamp(value))}>
          Bid {value}
        </button>
      </div>
    </div>
  );
}

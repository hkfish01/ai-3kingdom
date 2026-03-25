export type SpriteDirection = "up" | "down" | "left" | "right";
export type SpriteActivity = "walk" | "farm" | "play";

interface RpgSpriteAgentProps {
  sheetSrc: string;
  direction: SpriteDirection;
  activity: SpriteActivity;
  moving: boolean;
  tick: number;
  scale?: number;
}

interface SpriteSheetConfig {
  cols: number;
  rows: number;
  frameWidth: number;
  frameHeight: number;
  rowDown: number;
  rowUp: number;
  rowSide: number;
  idleFrame: number;
  walkFrames: number[];
  specialFrames: number[];
}

const RPG_3X7_CONFIG: SpriteSheetConfig = {
  cols: 7,
  rows: 3,
  frameWidth: 16,
  frameHeight: 16,
  rowDown: 0,
  rowUp: 1,
  rowSide: 2,
  idleFrame: 0,
  walkFrames: [1, 2, 3, 2],
  specialFrames: [4, 5, 6, 5]
};

function resolveRow(direction: SpriteDirection, cfg: SpriteSheetConfig): number {
  if (direction === "up") return cfg.rowUp;
  if (direction === "down") return cfg.rowDown;
  return cfg.rowSide;
}

function resolveFrameCol(activity: SpriteActivity, moving: boolean, tick: number, cfg: SpriteSheetConfig): number {
  if (!moving && activity === "walk") {
    return cfg.idleFrame;
  }
  const seq = activity === "walk" ? cfg.walkFrames : cfg.specialFrames;
  return seq[tick % seq.length] ?? cfg.idleFrame;
}

function framePosition(col: number, row: number, cfg: SpriteSheetConfig): { x: number; y: number } {
  const x = cfg.cols <= 1 ? 0 : (col / (cfg.cols - 1)) * 100;
  const y = cfg.rows <= 1 ? 0 : (row / (cfg.rows - 1)) * 100;
  return { x, y };
}

export default function RpgSpriteAgent({
  sheetSrc,
  direction,
  activity,
  moving,
  tick,
  scale = 2.0
}: RpgSpriteAgentProps) {
  const cfg = RPG_3X7_CONFIG;
  const row = resolveRow(direction, cfg);
  const col = resolveFrameCol(activity, moving, tick, cfg);
  const pos = framePosition(col, row, cfg);
  const isMirrored = direction === "right";

  return (
    <div
      className={`rpg-sprite-wrap ${isMirrored ? "rpg-sprite-mirror" : ""}`}
      style={{ width: `${cfg.frameWidth * scale}px`, height: `${cfg.frameHeight * scale}px` }}
      aria-label={`rpg sprite ${activity} ${direction}`}
    >
      <div
        className="rpg-sprite"
        style={{
          width: `${cfg.frameWidth * scale}px`,
          height: `${cfg.frameHeight * scale}px`,
          backgroundImage: `url(${sheetSrc})`,
          backgroundSize: `${cfg.cols * 100}% ${cfg.rows * 100}%`,
          backgroundPosition: `${pos.x}% ${pos.y}%`
        }}
      />
      <div className="rpg-sprite-shadow" />
    </div>
  );
}

export type PixelProfession = "farmer" | "merchant" | "guard" | "scholar" | "artisan" | "noble";

interface PixelSpriteAgentProps {
  profession: PixelProfession;
  task: string;
  moving: boolean;
  facingLeft: boolean;
}

function actionByTask(task: string): "walk" | "farm" | "play" {
  if (["farm", "irrigation", "expand_land"].includes(task)) {
    return "farm";
  }
  if (task === "play") {
    return "play";
  }
  return "walk";
}

export default function PixelSpriteAgent({ profession, task, moving, facingLeft }: PixelSpriteAgentProps) {
  const action = actionByTask(task);
  const sheet = `/pixel/agents/${profession}-${action}.svg`;
  const animate = moving || action === "farm" || action === "play";

  return (
    <div className={`pixel-sprite-wrap ${facingLeft ? "pixel-flip" : ""}`} aria-label={`pixel agent ${profession} ${task}`}>
      <div className={`pixel-sprite ${animate ? "pixel-sprite-anim" : ""}`} style={{ backgroundImage: `url(${sheet})` }} />
      <div className="pixel-shadow" />
    </div>
  );
}

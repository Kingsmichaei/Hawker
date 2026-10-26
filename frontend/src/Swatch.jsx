import { swatchSeed } from "./lib";

// A small generated adire-style cloth swatch, so products without photos still look like cloth.
const DYES = ["#17204a", "#2b4594", "#3c5fb8", "#1f3270", "#5a3d0f", "#c7891c"];

export default function Swatch({ name, image, className = "" }) {
  if (image) return <img src={image} alt="" className={`object-cover ${className}`} />;
  const s = swatchSeed(name);
  const dye = DYES[s % DYES.length];
  const kind = (s >> 3) % 3;
  const id = `sw${s}`;
  return (
    <svg viewBox="0 0 80 80" preserveAspectRatio="xMidYMid slice" className={className} aria-hidden="true">
      <defs>
        <pattern id={id} width="20" height="20" patternUnits="userSpaceOnUse" patternTransform={`rotate(${(s % 4) * 15})`}>
          <rect width="20" height="20" fill={dye} />
          {kind === 0 && <circle cx="10" cy="10" r="4" fill="none" stroke="#fff" strokeOpacity=".7" strokeWidth="1.5" />}
          {kind === 1 && <path d="M0 10h20M10 0v20" stroke="#fff" strokeOpacity=".55" strokeWidth="2" />}
          {kind === 2 && <path d="M0 20L10 0L20 20" fill="none" stroke="#fff" strokeOpacity=".6" strokeWidth="1.5" />}
          <circle cx="0" cy="0" r="1.6" fill="#fff" fillOpacity=".8" />
        </pattern>
      </defs>
      <rect width="80" height="80" fill={`url(#${id})`} />
    </svg>
  );
}

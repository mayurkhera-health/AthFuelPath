import Image from "next/image";

/**
 * A real capture from the app, inside the same bezel the coded mock screens use.
 *
 * Differences from <Device>: no notch overlay (the captures start at the app's
 * own header, so a notch would sit on top of the title), and the frame takes the
 * capture's true aspect ratio rather than the 9/19.3 the mocks were drawn to —
 * otherwise the image is cropped or letterboxed inside the bezel.
 *
 * `priority` only on the hero's front device; everything else lazy-loads.
 *
 * `unoptimized` bypasses /_next/image and serves the source file as it is.
 * Sparingly, and only where the source is already the right format at roughly
 * the right size — see the note at its one call site in Hero.tsx.
 */
export function Shot({
  src,
  alt,
  w,
  h,
  className = "",
  width,
  priority = false,
  unoptimized = false,
}: {
  src: string;
  alt: string;
  w: number;
  h: number;
  className?: string;
  width?: number;
  priority?: boolean;
  unoptimized?: boolean;
}) {
  return (
    <div
      className={`device device--shot ${className}`.trim()}
      style={{
        ["--dw" as string]: width ? `${width}px` : undefined,
        ["--ar" as string]: `${w} / ${h}`,
      }}
    >
      <div className="device__screen">
        <Image
          src={src}
          alt={alt}
          width={w}
          height={h}
          priority={priority}
          unoptimized={unoptimized}
          sizes="(max-width: 1023px) 300px, 320px"
        />
      </div>
    </div>
  );
}

// The outer headphone joint departs independently of the body/gear springs.
const WORN = Object.freeze({
  opacity: 1,
  lift: 0,
  spread: 0,
  angle: 0,
  scale: 1,
});
const GONE = Object.freeze({ ...WORN, opacity: 0 });
const smooth = (t) => t * t * (3 - 2 * t);
const REMOVAL = [
  [0, WORN],
  [0.12, { opacity: 1, lift: 2, spread: 2, angle: 0, scale: 1.02 }],
  [0.36, { opacity: 1, lift: -19, spread: 7, angle: -6, scale: 1.04 }],
  [0.6, { opacity: 0.75, lift: -34, spread: 9, angle: -10, scale: 0.98 }],
  [0.85, { opacity: 0, lift: -46, spread: 11, angle: -14, scale: 0.9 }],
];

/** No prior listening state means there are no headphones to remove. */
export function sampleHeadphones(
  mood,
  age,
  { departing = false, reduced = false } = {},
) {
  if (mood === "listening") return WORN;
  if (mood !== "submitted" || !departing || reduced) return GONE;
  if (age >= 0.85) return { ...REMOVAL.at(-1)[1] };
  const time = Math.max(0, age);
  let index = 0;
  while (index < REMOVAL.length - 2 && time > REMOVAL[index + 1][0]) index++;
  const [start, from] = REMOVAL[index],
    [end, to] = REMOVAL[index + 1];
  const blend = smooth((time - start) / (end - start));
  return Object.fromEntries(
    Object.keys(WORN).map((key) => [
      key,
      from[key] + (to[key] - from[key]) * blend,
    ]),
  );
}

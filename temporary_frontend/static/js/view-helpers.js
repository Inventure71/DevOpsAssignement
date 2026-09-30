export const characters = {vinyl: "◉", bolt: "ϟ", moon: "☾", sun: "☀", ghost: "♧", flower: "✿", wave: "≋", star: "★"};
export const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[c]));
export const icon = id => characters[id] || characters.vinyl;

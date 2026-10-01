// Persisted IDs select color. Every preset uses the same body and rig.
export const BLOB_COLORS = Object.freeze(
  [
    {
      id: "coral",
      label: "Coral",
      main: "#f5ad9f",
      light: "#ffe0d6",
      dark: "#df8f85",
      accent: "#d97569",
    },
    {
      id: "periwinkle",
      label: "Periwinkle",
      main: "#acb9ef",
      light: "#e0e6ff",
      dark: "#889bd8",
      accent: "#667bc9",
    },
    {
      id: "lavender",
      label: "Lavender",
      main: "#c5ace8",
      light: "#eee1fc",
      dark: "#a58bcc",
      accent: "#8e68c2",
    },
    {
      id: "lemon",
      label: "Lemon",
      main: "#f9df95",
      light: "#fff3cd",
      dark: "#e2c16f",
      accent: "#a78124",
    },
    {
      id: "lilac",
      label: "Lilac",
      main: "#dec4ee",
      light: "#f6e8fc",
      dark: "#c0a3d4",
      accent: "#ab7abd",
    },
    {
      id: "sage",
      label: "Sage",
      main: "#bdceae",
      light: "#e8efd9",
      dark: "#9cad91",
      accent: "#6e8b59",
    },
    {
      id: "sky",
      label: "Sky",
      main: "#b4cfee",
      light: "#e2f0ff",
      dark: "#93acd0",
      accent: "#5f8cb9",
    },
    {
      id: "rose",
      label: "Rose",
      main: "#edbdd4",
      light: "#ffe8f2",
      dark: "#ce9bb6",
      accent: "#b66d94",
    },
  ].map(Object.freeze),
);
export function getBlobColor(id) {
  return BLOB_COLORS.find((color) => color.id === id) ?? BLOB_COLORS[0];
}

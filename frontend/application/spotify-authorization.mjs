// Provider URL policy stays separate from the shared admission lifecycle.
export function spotifyApplication(config, location, code) {
  if (config.requires_shared_url)
    throw new Error("Spotify is configured for the server computer only. The host must finish network setup before other devices can sign in.");
  const application = new URL(config.application_url);
  if (!["http:", "https:"].includes(application.protocol) || application.username || application.password)
    throw new Error("The Spotify application URL is invalid.");
  if (application.origin !== location.origin) {
    if (code) application.searchParams.set("join", code);
    return application.href;
  }
  return null;
}

export function spotifyAuthorization(authorization) {
  if (authorization?.kind !== "redirect")
    throw new Error("The Spotify authorization response is invalid.");
  const address = new URL(authorization.url);
  if (address.origin !== "https://accounts.spotify.com" || address.pathname !== "/authorize" || address.username || address.password)
    throw new Error("The Spotify authorization address is invalid.");
  return address.href;
}

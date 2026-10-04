import { spotifyApplication, spotifyAuthorization } from "./spotify-authorization.mjs";

// Implemented authorization strategies; deferred providers appear in capabilities.
export const musicAuthorization = Object.freeze({
  spotify: Object.freeze({ application: spotifyApplication, authorization: spotifyAuthorization }),
});

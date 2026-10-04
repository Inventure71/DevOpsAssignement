import { element, text } from "../dom.mjs";

// Static help and about content; the caller owns navigation and room state.
export function createInfoScreen(page, navigate) {
  const section = element(
    '<section class="info-screen"><h1></h1><div></div><button class="button button-primary">Back to play →</button></section>',
  );
  text(
    section.querySelector("h1"),
    page === "how" ? "How to play" : "Who’s On Repeat",
  );
  const content = section.querySelector("div");
  if (page === "how") {
    const steps = document.createElement("ol");
    for (const description of [
      "Create a room and share its code. Everyone joins on their own screen.",
      "Enable sound on the host’s device so everyone can hear its speaker. Each round starts with a synced countdown.",
      "Search for the song and select the friends you think listen to it. Submit once before time runs out.",
      "See the song, everyone’s guesses and the leaderboard. An empty player selection means nobody.",
    ]) {
      const item = document.createElement("li");
      item.textContent = description;
      steps.append(item);
    }
    content.append(steps);
  } else {
    const paragraph = document.createElement("p");
    paragraph.textContent =
      "A music guessing game for friends. The host plays too, and everyone answers on their own screen.";
    content.append(paragraph);
    const credits = document.createElement("a");
    credits.href = "/music-credits";
    credits.textContent = "Music credits";
    credits.target = "_blank";
    credits.rel = "noopener";
    content.append(credits);
  }
  section
    .querySelector("button")
    .addEventListener("click", () => navigate("play"));
  return { element: section, update() {}, destroy() {} };
}

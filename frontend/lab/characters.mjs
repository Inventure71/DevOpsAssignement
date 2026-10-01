import "../components/color-picker.mjs";
import { BLOB_COLORS } from "../components/blob-palette.mjs";
import { element, text } from "../dom.mjs";

export function createCharacterStudio() {
  const section = element(`
    <section class="character-lab"><h1>Meet your blob.</h1>
      <p>Pick a color, change its mood, or tap to react.</p>
      <div class="blob-studio"><repeat-character class="studio-character" color="coral" mood="listening"></repeat-character>
        <div class="studio-controls"><blob-color-picker value="coral"></blob-color-picker>
          <label class="lab-mood">Mood <select aria-label="Mood"><option value="listening">Listening</option><option value="submitted">Submitted</option><option value="idle">Idle</option><option value="celebrating">Celebrating</option><option value="sad">Sad</option></select></label>
          <div class="studio-reactions"><button type="button" class="button button-soft" data-reaction="poke">Squish</button><button type="button" class="button button-soft" data-reaction="greet">Say hello</button></div>
        </div>
      </div><div class="specimen-grid"></div>
    </section>`);
  const mainBlob = section.querySelector(".studio-character");
  section
    .querySelector("blob-color-picker")
    .addEventListener("color-select", (event) => {
      mainBlob.setAttribute("color", event.detail.color);
      mainBlob.react("greet");
    });
  for (const button of section.querySelectorAll("[data-reaction]"))
    button.addEventListener("click", () =>
      mainBlob.react(button.dataset.reaction),
    );
  const grid = section.querySelector(".specimen-grid");
  for (const color of BLOB_COLORS) {
    const item = element(
      '<figure><repeat-character mood="listening"></repeat-character><figcaption></figcaption></figure>',
    );
    item.querySelector("repeat-character").setAttribute("color", color.id);
    text(item.querySelector("figcaption"), color.label);
    grid.append(item);
  }
  section.querySelector("select").addEventListener("change", (event) => {
    for (const sprite of section.querySelectorAll("repeat-character"))
      sprite.setAttribute("mood", event.target.value);
  });
  return section;
}

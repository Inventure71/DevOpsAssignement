import { createLabController } from "./lab/controller.mjs";

createLabController({
  root: document.querySelector("#main"),
  navigation: document.querySelector(".lab-nav"),
  params: new URLSearchParams(location.search),
}).start();
